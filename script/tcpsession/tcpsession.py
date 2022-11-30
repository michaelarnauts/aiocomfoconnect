#!/usr/bin/env python3
# -*- coding: ISO-8859-15 -*-

import binascii
import copy
import json
import logging
import os
import socket
import struct
from collections import deque
from enum import Enum
from hashlib import md5, sha256
from typing import ClassVar, Iterable

import dpkt

"""
MSL (Maximum Segment Life) is arbitrarily chosen to be 2 minutes in TCP
It is the maximum time a segment can be in a network
"""

# https://tools.ietf.org/html/rfc793#page-19, only set during Handshake, if not specified any MSS can be used
# https://tools.ietf.org/html/rfc1323#page-8
# Window size rwnd (including the scaling factor) is set during the TCP handshake, it can't be changed afterwards
# only CWND(congestion window) -- which is in multiple of MSS -- can be adjusted on sender side based on the ACKs
# received.
# https://en.wikipedia.org/wiki/TCP_window_scale_option
# TODO: If wrong timestamp is sent by the peer - this behavior is not handled in code.
# TODO: If MSS, or Window size is sent after handshake - this behavior is also not handled.


# TODO: decide the right way to handle the case when a node sends data beyond the current window,
#  currently it's discarded.
# TODO: fix the issue in json output where \x00 is dumped as \u0000 (unicoded), it will not be
#  compatible with program ingesting the json not written in python

MAX_SEQ_NUM = 0xFFFFFFFF
SEQ_NUM_MOD_CONST = 0x100000000
MAX_TCP_WINDOW_SIZE = 0xFFFF
MAX_TCP_WINDOW_SIZE_WITH_OPTIONS = 0xFFFF * 0x4000
TCP_MSS_1460 = b"\x05\xb4"
TCP_MSS_DEFAULT_BYTES = b'\x02\x18'
TCP_MSS_DEFAULT = 536
TCP_MSS_OPTION_PREFIX = b"\x02\x04"
TCP_NOP_OPTION_PAYLOAD = b"\x01"
TCP_END_OF_OPTION_LIST_OPTION_PAYLOAD = b"\x00"
TCP_WINDOW_SCALE_OPTION_PREFIX = b"\x03\x03"
TCP_TIME_STAMP_OPTION_PREFIX = b"\x08\x0A"
TCP_SELECTIVE_ACK_PERMITTED_OPTION = b'\x04\x02'
TCP_SELECTIVE_ACK = b'\x05'
UNKNOWN_OPTION_PREFIX = "UKNOWN_OPTION_"
logger = logging.getLogger(__name__)


def tcp_option_window_scale_payload(shift_count: int) -> bytes:
    """
    :param shift_count: number of bits to shift
    :return: bytes representation of the TCP window scale option
    """
    if 0 <= shift_count <= 14:
        return TCP_WINDOW_SCALE_OPTION_PREFIX + struct.pack('>B', shift_count)
    return b""


def tcp_option_mss_paylod(mss: int) -> bytes:
    """
    :param mss: maximum segment size
    :return: bytes representation of the TCP MSS option
    """
    if 0 <= mss <= 0xFFFF:
        return TCP_MSS_OPTION_PREFIX + struct.pack(">H", mss)
    return b''


def tcp_option_time_stamp_payload(time_stamp_val: int, time_stamp_echo_reply: int) -> bytes:
    """
    :param time_stamp_val: current value of the timestamp clock of the TCP sending the option
    :param time_stamp_echo_reply: timestamp value that was sent by the remote TCP in the TSval field of a timestamp
    :return: bytes representation of the TCP Timestamps option
    """
    if (0 <= time_stamp_val <= 0xFFFFFFFF and
            0 <= time_stamp_echo_reply <= 0xFFFFFFFF):
        return (TCP_TIME_STAMP_OPTION_PREFIX + struct.pack(">I", time_stamp_val) +
                struct.pack(">I", time_stamp_echo_reply))
    return b''


def tcp_option_payload_creation(option_payloads: list) -> bytes:
    """
    Create 32 bit aligned options up to 40 bytes, options after that are discarded
    :param option_payloads: list of options in bytes
    :return: bytes of payload ensuring 32 bit boundary aligned
    """
    payload = b''
    for option in option_payloads:
        if len(option) + len(payload) > 40:
            break
        payload += option
    payload += TCP_NOP_OPTION_PAYLOAD * (4 - (len(payload) % 4))
    return payload


def hash_digest(data: bytes, hash_algo: str = "sha256") -> bytes:
    """ Returns the hash digest digest of the given input data in hex
    :param data: input data which hash digest in hex is desired
    :param hash_algo: which hash digest is desired
    :return: hash digest in hex representation
    """
    if hash_algo == "sha256":
        digester = sha256()
        digester.update(data)
        return digester.hexdigest()


def create_tcp_pkt(smac: bytes, dmac: bytes, sip: bytes, dip: bytes, ip_id: int, sp: int, dp: int,
                   flags: int = dpkt.tcp.TH_SYN, payload: bytes = b"") -> dpkt.ethernet.Ethernet:
    """ Crates a Ethernet packet containing IP and TCP header
    :param smac: source MAC address
    :param dmac: destination MAC address
    :param sip: source IP address
    :param dip: destination address
    :param ip_id: IP packet identifier
    :param sp: source port number
    :param dp: destination port number
    :param flags: TCP flag
    :param payload: TCP payload
    :return: Ethernet object
    """
    tcp_pkt = dpkt.tcp.TCP(sport=sp, dport=dp, flags=flags)
    tcp_pkt.data = payload
    ip_pkt = dpkt.ip.IP(id=ip_id, p=6, src=sip, dst=dip)
    ip_pkt.data = tcp_pkt
    ip_pkt.len += len(ip_pkt.data)
    eth_pkt = dpkt.ethernet.Ethernet(src=smac, dst=dmac)
    eth_pkt.data = ip_pkt
    return eth_pkt


def duplicate_tcp_pkt(src_pkt: dpkt.ethernet.Ethernet, seq: int, ack: int, flags: int = dpkt.tcp.TH_ACK,
                      payload: bytes = b"") -> dpkt.ethernet.Ethernet:
    """Creates a duplicate TCP packet with updated specified fields parameters values
    :param src_pkt: Ethernet object of a packet to duplicate, it must contains TCP data
    :param seq: new TCP sequence number
    :param ack: new TCP acknowledgement number
    :param flags: TCP flags
    :param payload: new TCP payload
    :return: new Ethernet object
    """
    new_pkt = copy.deepcopy(src_pkt)
    new_pkt.data.data.seq = seq
    new_pkt.data.data.ack = ack
    new_pkt.data.data.flags = flags
    new_pkt.data.data.data = payload
    if payload:
        new_pkt.data.len -= src_pkt.data.len - (4 * src_pkt.data.hl) - (4 * src_pkt.data.data.off)
        new_pkt.data.len += len(payload)
    new_pkt = tcp_fix_checksum(new_pkt)
    return new_pkt


def craft_tcp_packet_with_options(pkt: dpkt.ethernet.Ethernet, opts: list) -> dpkt.ethernet.Ethernet:
    """Updates a TCP packet with options provided in the parameter as a list. Input Ethernet packet must contain IP and
       TCP header.
    :param pkt: Input packet to fill list of options into
    :param opts: list of TCP options
    :return: Ethernet packet with TCP options
    """
    if isinstance(pkt, dpkt.ethernet.Ethernet) and isinstance(pkt.data.data, dpkt.tcp.TCP):
        pkt.data.data.opts = tcp_option_payload_creation(opts)
        pkt.data.data.off = 5 + int(len(pkt.data.data.opts) / 4)
        pkt.data = tcp_fix_checksum(pkt.data)
        return pkt
    return b''


def get_tcp_packet_payload_len_with_options(pkt: dpkt.ethernet.Ethernet) -> int:
    """
        Return the length of payload including options
    :param pkt: dpkt.ethernet.Ethernet packet containing TCP header
    :return: int
    """
    if isinstance(pkt, dpkt.ethernet.Ethernet):
        ip = pkt.data
    elif isinstance(pkt, dpkt.ip.IP):
        ip = pkt
    else:
        return None
    return ip.len - ip.hl * 4 - 20


def get_tcp_packet_payload_len(pkt: dpkt.ethernet.Ethernet) -> int:
    """
        Return the length of only payload without options
    :param pkt: dpkt.ethernet.Ethernet packet containing TCP header
    :return: int
    """
    if isinstance(pkt, dpkt.ethernet.Ethernet):
        ip = pkt.data
    elif isinstance(pkt, dpkt.ip.IP):
        ip = pkt
    else:
        return None
    return ip.len - (ip.hl * 4 + ip.data.off * 4)


def get_tcp_packet_payload(pkt: dpkt.ethernet.Ethernet) -> bytes:
    """Returns the TCP payload in Ethernet packet. Provided input pkt must contain IP and TCP headers
    :param pkt: input packet to get the TCP payload from
    :return: TCP payload
    """
    eth = dpkt.ethernet.Ethernet(pkt)
    if isinstance(eth.data, dpkt.ip.IP) and isinstance(eth.data.data, dpkt.tcp.TCP):
        return eth.data.data.data


def inet_to_str(inet) -> str:
    """Convert inet object to a string

        Args:
            inet (inet struct): inet network address
        Returns:
            str: Printable/readable IP address
    """
    # First try ipv4 and then ipv6
    try:
        return socket.inet_ntop(socket.AF_INET, inet)
    except ValueError:
        return socket.inet_ntop(socket.AF_INET6, inet)


def str_to_inet(ip: str) -> bytes:
    """
    Converts a string representation of IP address to binary representation.
    :param ip: IP like - "123.45.67.89"
    :return: 32 bit representation of "123.45.67.89" like - '{-CY'
    """
    try:
        return socket.inet_pton(socket.AF_INET, ip)
    except OSError:
        return socket.inet_pton(socket.AF_INET6, ip)


def tcp_fix_checksum_buf(buf: bytes) -> bytes:
    """ Fixes the IP and TCP check sum
    :param buf: bytes of Ethernet packet containing IP and TCP header
    :return: bytes of Bytes of Ethernet packet containing IP and TCP header with fixed IP and TCP checksum
    """
    pkt = dpkt.ethernet.Ethernet(buf)
    ip = pkt.data
    ip.sum = 0
    ip.sum = dpkt.in_cksum(ip.pack_hdr() + bytes(ip.opts))
    tcp = ip.data
    tcp.sum = 0
    payload = bytes(tcp)
    _sum = dpkt.struct.pack('>4s4sxBH', ip.src, ip.dst, ip.p, len(payload))
    _sum = dpkt.in_cksum_add(0, _sum)
    _sum = dpkt.in_cksum_add(_sum, payload)
    tcp.sum = dpkt.in_cksum_done(_sum)
    return pkt.pack()


def tcp_fix_checksum(pkt: dpkt.ethernet.Ethernet) -> dpkt.ethernet.Ethernet:
    """Fixes the IP and TCP checksum in Ethernet packet, it must contain TCP and IP header
    :param pkt: input Ethernet packet
    :return: Ethernet object with fixed IP and TCP checksum
    """
    if isinstance(pkt, dpkt.ethernet.Ethernet):
        ip = pkt.data
    elif isinstance(pkt, dpkt.ip.IP):
        ip = pkt
    else:
        return None
    tcp = ip.data
    tcp.sum = 0
    payload = bytes(tcp)
    _sum = dpkt.struct.pack('>4s4sxBH', ip.src, ip.dst, ip.p, len(payload))
    _sum = dpkt.in_cksum_add(0, _sum)
    _sum = dpkt.in_cksum_add(_sum, payload)
    tcp.sum = dpkt.in_cksum_done(_sum)
    ip.data = tcp
    ip.sum = 0
    if isinstance(pkt, dpkt.ethernet.Ethernet):
        ip.sum = dpkt.in_cksum(ip.pack_hdr() + bytes(ip.opts))
        pkt.data = ip
    return pkt


def tcp_checksum_calc(src: bytes, dst: bytes, proto: int, payload: bytes) -> bytes:
    """Calculate checksum of a TCP header
    :param src: source IP address
    :param dst: destination IP address
    :param proto: TCP protocol
    :param payload: TCP payload
    :return: checksum
    """
    _sum = dpkt.struct.pack(">4s4sxBH", src, dst, proto, len(payload))
    _sum = dpkt.in_cksum_add(0, _sum)
    _sum = dpkt.in_cksum_add(_sum, payload)
    _sum = dpkt.in_cksum_done(_sum)
    return _sum


def tcp_shasum_calc(src: bytes, dst: bytes, proto: int, payload: bytes) -> bytes:
    """ Calculate SHA256 sum of a TCP header
    :param src: source IP address
    :param dst: destination IP address
    :param proto: TCP protocol
    :param payload: TCP payload
    :return: SHA256 sum
    """
    _sum = struct.pack(">4s4sxBH", src, dst, proto, len(payload))
    if isinstance(payload, str):
        payload = payload.encode()
    return hash_digest(_sum + payload)


def inc_tcp_seq_number(cur_seq: int, inc_by: int) -> int:
    """ Increment a TCP sequence number by a number
    :param cur_seq: TCP sequence number
    :param inc_by: number to increment given input cur_seq by
    :return: incremented sequence number
    """
    if cur_seq < 0:
        return None
    return (cur_seq + inc_by) % SEQ_NUM_MOD_CONST


def seq_number_off_by_window(seq: int, win_start_seq: int, window_size: int) -> int:
    """ This returns how a sequence number is off from a TCP window
    :param seq: a TCP seq number
    :param win_start_seq: a sequence number where current TCP window start
    :param window_size: size of the TCP window
    :return: int
    """
    if seq < 0 or win_start_seq < 0:
        return None
    if tcp_seq_number_in_window(win_start_seq, seq, window_size):
        # seq is ahead of or at the win_start_seq in window and returned value would be -ve or 0
        if seq >= win_start_seq:
            return win_start_seq - seq
        else:
            return win_start_seq - SEQ_NUM_MOD_CONST - seq
    else:
        # seq is not in the window starting at end_seq
        prev_win_start = (win_start_seq - window_size) % SEQ_NUM_MOD_CONST
        if tcp_seq_number_in_window(prev_win_start, seq, window_size):
            # If seq is from previous window then it's considered as late delivery, and it's behind current window
            # starting at win_start_seq (so we will return what's equivalent of win_start_seq - seq.
            return seq_numbers_diff(seq, win_start_seq)
        else:
            # Else, it's seq is ahead of the window we will return what's equivalent of
            # (seq - win_start_seq)%window_size + 1
            return seq_numbers_diff(win_start_seq, seq) % window_size + 1
            # return (seq - win_start_seq) % window_size + 1


def seq_numbers_diff(start_seq: int, end_seq: int) -> int:
    """Difference between two sequence numbers, this assumes that end_seq is always ahead of start_seq
    :param start_seq: TCP sequence number
    :param end_seq: another TCP sequence number
    :return: difference between two sequence numbers
    """
    if start_seq < 0 or end_seq < 0:
        return None
    if start_seq > end_seq:
        return end_seq + (SEQ_NUM_MOD_CONST - start_seq)
    else:
        return end_seq - start_seq


def tcp_seq_number_in_window(start_seq_number: int, in_seq_number: int,
                             win_size: int = MAX_TCP_WINDOW_SIZE_WITH_OPTIONS):
    """Checks if a sequence number is in a TCP window starting at start_seq_number of size win_size
    :param start_seq_number: TCP window starting sequence number
    :param in_seq_number: input TCP sequence number to check if it's in the window
    :param win_size: size of the TCP window
    :return: True if in_seq_number is in the window, else false
    """
    if win_size > MAX_TCP_WINDOW_SIZE_WITH_OPTIONS:
        return None
    window_start = start_seq_number
    window_end = inc_tcp_seq_number(start_seq_number, win_size)
    if window_end is None:
        return None
    if window_end >= window_start:
        if window_start <= in_seq_number < window_end:
            return True
    else:
        if window_start <= in_seq_number <= MAX_SEQ_NUM or in_seq_number < window_end:
            return True
    return False


def tcp_pkt_debug_info(pkt: dpkt.ip.IP) -> str:
    """ IP packet information in string representation
    :param pkt: input IP packet to print
    :return: string representation of the input packet
    """
    if isinstance(pkt, dpkt.ip.IP):
        paylod_len = pkt.len - (4 * pkt.hl) - (4 * pkt.data.off)
        return "{}:{}-> {}:{}, seq: {}, ack:{}, flag:{}, payload len: {}, payload: {}, sum: {}".format(
            inet_to_str(pkt.src), pkt.data.sport, inet_to_str(pkt.dst), pkt.data.dport, hex(pkt.data.seq),
            hex(pkt.data.ack), hex(pkt.data.flags), hex(paylod_len), pkt.data.data, hex(pkt.data.sum))


def tcp_pkt_parse_options(options: bytes) -> dict:
    """Converts well formed TCP options in bytes into a dictionary of option name and it's value.
    :param options: TCP options in bytes
    :return: dictionary of TCP options
    """
    i = 0
    options_dict = dict()
    opts_rev_mapping = enum_value_to_enum(TCPOptions)
    while i < len(options):
        prefix = options[i]
        i += 1
        if prefix == dpkt.tcp.TCP_OPT_EOL or prefix == dpkt.tcp.TCP_OPT_NOP:
            options_dict[opts_rev_mapping[prefix]] = (0, None)
        else:
            if i < len(options):
                opt_len = options[i]
                i += 1
                if prefix in opts_rev_mapping.keys():
                    options_dict[opts_rev_mapping[prefix]] = (opt_len, options[i:i + opt_len - 2])
                else:
                    options_dict[UNKNOWN_OPTION_PREFIX + str(prefix)] = (opt_len, options[i:i + opt_len - 2])
                i += opt_len - 2
            else:
                break
    return options_dict


def tcp_pkt_options_debug_info(pkt: dpkt.tcp.TCP) -> str:
    """Returns printable string representation of TCP options
    :param pkt: TCP packet with options
    :return: string representation of TCP options
    """
    str_repr_list = []
    if isinstance(pkt, dpkt.tcp.TCP) and pkt.opts:
        opts_dict = tcp_pkt_parse_options(pkt.opts)
        for opt_kind in opts_dict.keys():
            str_repr = ""
            if type(opt_kind) is str and opt_kind.startswith(UNKNOWN_OPTION_PREFIX):
                str_repr += "Kind: {}, name: {}, len: {}, data: {}".format(
                    hex(int(opt_kind.split(UNKNOWN_OPTION_PREFIX)[1])), opt_kind, opts_dict[opt_kind][0],
                    binascii.hexlify(opts_dict[opt_kind][1]).decode('utf-8'))
            else:
                str_repr += "Kind: {}, name: {} ".format(hex(opt_kind.value), opt_kind.name)
            if opt_kind == TCPOptions.TCP_OPT_SACK:
                _len = opts_dict[opt_kind][0]
                str_repr += "length: {} ".format(_len)
                _len -= 2
                s_acks = opts_dict[opt_kind][1]
                for i in range(0, _len, 8):
                    str_repr += "left edge of block: {}, right edge of block: {}, ".format(
                        binascii.hexlify(s_acks[i:i + 4]).decode('utf-8'),
                        binascii.hexlify(s_acks[i + 4:i + 8]).decode('utf-8'))
            elif opt_kind == TCPOptions.TCP_OPT_TIMESTAMP:
                str_repr += "length: {}, timestamp value: {}, timestamp echo reply: {}".format(
                    opts_dict[opt_kind][0], binascii.hexlify(opts_dict[opt_kind][1][:4]).decode('utf-8'),
                    binascii.hexlify(opts_dict[opt_kind][1][4:]).decode('utf-8'))
            elif not (type(opt_kind) == str or opt_kind == TCPOptions.TCP_OPT_NOP or
                      opt_kind == TCPOptions.TCP_OPT_EOL):
                str_repr += "length: {}, data: {}".format(opts_dict[opt_kind][0],
                                                          binascii.hexlify(opts_dict[opt_kind][1]).decode('utf-8'))
            str_repr_list.append(str_repr)
    return "Options: " + str(str_repr_list)


def tcp_opts_tuple_list_to_dict(opts_list: list) -> dict:
    """Convert tuple of TCP options to a dictionary
    :param opts_list: list of TCP options tuple
    :return: diction of TCP options
    """
    opts = {}
    if None in opts_list:
        opts_list.remove(None)
    for opt, value in opts_list:
        # here TCP_OPT_NOP is saved only once, even though multiple TCP_OPT_NOP might be present
        # since it doesn't affect our operations, or at least I couldn't think of one, so it's okay to overwrite it
        opts[opt] = value
    return opts


def enum_value_to_enum(enum_class: Enum) -> dict:
    """
    :param enum_class: your enum class which should be subclass of enum.Enum
    :return: dict of value -> enum member mapping
    """
    res = dict()
    for member in enum_class:
        res[member.value] = member
    return res


class TCPOptions(Enum):
    """Enum class for TCP options
    """
    # Options (opt_type) - http://www.iana.org/assignments/tcp-parameters
    TCP_OPT_EOL = dpkt.tcp.TCP_OPT_EOL  # end of option list
    TCP_OPT_NOP = dpkt.tcp.TCP_OPT_NOP  # no operation
    TCP_OPT_MSS = dpkt.tcp.TCP_OPT_MSS  # maximum segment size
    TCP_OPT_WSCALE = dpkt.tcp.TCP_OPT_WSCALE  # window scale factor, RFC 1072
    TCP_OPT_SACKOK = dpkt.tcp.TCP_OPT_SACKOK  # SACK permitted, RFC 2018
    TCP_OPT_SACK = dpkt.tcp.TCP_OPT_SACK  # SACK, RFC 2018
    TCP_OPT_ECHO = dpkt.tcp.TCP_OPT_ECHO  # echo (obsolete), RFC 1072
    TCP_OPT_ECHOREPLY = dpkt.tcp.TCP_OPT_ECHOREPLY  # echo reply (obsolete), RFC 1072
    TCP_OPT_TIMESTAMP = dpkt.tcp.TCP_OPT_TIMESTAMP  # timestamp, RFC 1323
    TCP_OPT_POCONN = dpkt.tcp.TCP_OPT_POCONN  # partial order conn, RFC 1693
    TCP_OPT_POSVC = dpkt.tcp.TCP_OPT_POSVC  # partial order service, RFC 1693
    TCP_OPT_CC = dpkt.tcp.TCP_OPT_CC  # connection count, RFC 1644
    TCP_OPT_CCNEW = dpkt.tcp.TCP_OPT_CCNEW  # CC.NEW, RFC 1644
    TCP_OPT_CCECHO = dpkt.tcp.TCP_OPT_CCECHO  # CC.ECHO, RFC 1644
    TCP_OPT_ALTSUM = dpkt.tcp.TCP_OPT_ALTSUM  # alt checksum request, RFC 1146
    TCP_OPT_ALTSUMDATA = dpkt.tcp.TCP_OPT_ALTSUMDATA  # alt checksum data, RFC 1146
    TCP_OPT_SKEETER = dpkt.tcp.TCP_OPT_SKEETER  # Skeeter
    TCP_OPT_BUBBA = dpkt.tcp.TCP_OPT_BUBBA  # Bubba
    TCP_OPT_TRAILSUM = dpkt.tcp.TCP_OPT_TRAILSUM  # trailer checksum
    TCP_OPT_MD5 = dpkt.tcp.TCP_OPT_MD5  # MD5 signature, RFC 2385
    TCP_OPT_SCPS = dpkt.tcp.TCP_OPT_SCPS  # SCPS capabilities
    TCP_OPT_SNACK = dpkt.tcp.TCP_OPT_SNACK  # selective negative acks
    TCP_OPT_REC = dpkt.tcp.TCP_OPT_REC  # record boundaries
    TCP_OPT_CORRUPT = dpkt.tcp.TCP_OPT_CORRUPT  # corruption experienced
    TCP_OPT_SNAP = dpkt.tcp.TCP_OPT_SNAP  # SNAP
    TCP_OPT_TCPCOMP = dpkt.tcp.TCP_OPT_TCPCOMP  # TCP compression filter
    TCP_OPT_MAX = dpkt.tcp.TCP_OPT_MAX
    TCP_OPT_UNKNOWN = 255


class TCPState(Enum):
    """Enum of TCP states"""
    CLOSED = 0
    LISTENING = 1
    SYN_SENT = 2
    SYN_RECEIVED = 3
    SYN_ACK_RECEIVED = 4
    SYN_ACK_SENT = 5
    ESTABLISHED = 6
    FIN_WAIT_1 = 7
    FIN_WAIT_2 = 8
    CLOSE_WAIT = 9
    LAST_ACK = 10
    CLOSING = 11
    TIME_WAIT = 12


class NetworkTuple:
    """Class to store a network tuple which could be used as a key in a dictionary or in a set.
    """

    def __init__(self, sip, dip, sp, dp, proto):
        self.sip = sip
        self.dip = dip
        self.sp = sp
        self.dp = dp
        self.proto = proto

    def get_str_sip(self) -> str:
        return inet_to_str(self.sip)

    def get_str_dip(self) -> str:
        return inet_to_str(self.dip)

    def __eq__(self, other: object):
        if (self.sip == other.sip and self.dip == other.dip and
                self.sp == other.sp and self.dp == other.dp and self.proto == other.proto):
            return True
        elif (self.sip == other.dip and self.dip == other.sip and self.sp == other.dp and self.dp == other.sp and
              self.proto == other.proto):
            return True
        else:
            return False

    def __ne__(self, other: object):
        return not self.__eq__(other)

    def __repr__(self):
        return "{}_{}-{}_{}-{}".format(inet_to_str(self.sip), self.sp, inet_to_str(self.dip), self.dp, self.proto)

    def __hash__(self) -> int:
        """Hash is calculated in a way that numerically small network node between source and destination comes before.
        For e.g. in between 12.2.2.2:80 and 12.2.2.2:81, former will come first; for 12.2.2.2:80 and 11.255.255.255:650,
        latter will come first. This is done to keep the hash value of Network Tuple of two ip and two ports same and
        unique, no matter which IP is source or destination, while keeping their ports fixed. For clarification,
        12.2.2.2:80 and 11.255.255.255:650, any of the node could be either source or destination, while keeping their
        ports fixed and hash would be same.

        :return: hash of the object.
        :rtype: int
        """
        sip_int_repr = struct.unpack(">I", self.sip)
        dip_int_repr = struct.unpack(">I", self.dip)
        if sip_int_repr < dip_int_repr:
            return hash(self.__repr__())
        elif sip_int_repr == dip_int_repr:
            if self.sp <= self.dp:
                return hash(self.__repr__())
        return hash("{}_{}-{}_{}-{}".format(inet_to_str(self.dip), self.dp, inet_to_str(self.sip), self.sp, self.proto))

    def __str__(self):
        return self.__repr__()


class TCPSession(object):
    """Class which extracts TCP sessions from a pcap
    """

    def __init__(self, inpcap: str, sip: str = "", dip: str = "", sp: int = 0, dp: int = 0, debug_info=False):
        self.sip = inet_to_str(sip)
        self.dip = inet_to_str(dip)
        self.sp = sp
        self.dp = dp
        self.pcap = inpcap
        self.sessions = dict()
        # stores data about the session_id - tuple of size of data sent from both the sides
        self.sessions_meta_data = dict()
        self.session_count = 0
        self._print_debug_info = debug_info
        self.pkt_num = 0
        self._c_state = TCPState.CLOSED
        self._s_state = TCPState.LISTENING
        self._s_seq = -1
        self._c_seq = -1
        self._c_prev_pkt_ind = -1
        self._s_prev_pkt_ind = -1
        self._c_rcv_next = 0
        self._s_rcv_next = 0
        self._c_win_left_edge = -1
        self._s_win_left_edge = -1
        self._c_early_pkts = deque()
        self._s_early_pkts = deque()
        self._c_win_size = -1
        self._s_win_size = -1
        self._c_win_scaling_factor = 0
        self._s_win_scaling_factor = 0
        self._c_mss = -1
        self._s_mss = -1
        self._c_payload_size = 0
        self._s_payload_size = 0
        logger.info("TCP session of network tuple: sip: {}, dip: {}, sp: {}, dp: {}".format(self.sip, self.dip, self.sp,
                                                                                            self.dp))

    def clear(self):
        self.__reset_state__()
        self.sessions = dict()
        self.session_count = 0

    def __reset_state__(self):
        self._c_state = TCPState.CLOSED
        self._s_state = TCPState.LISTENING
        self._s_seq = -1
        self._c_seq = -1
        self._c_prev_pkt_ind = -1
        self._s_prev_pkt_ind = -1
        self._c_rcv_next = 0
        self._s_rcv_next = 0
        self._c_win_left_edge = -1
        self._s_win_left_edge = -1
        self._c_early_pkts = deque()
        self._s_early_pkts = deque()
        self._c_win_size = -1
        self._s_win_size = -1
        self._c_win_scaling_factor = 0
        self._s_win_scaling_factor = 0
        self._c_mss = -1
        self._s_mss = -1
        self.sessions_meta_data[self.session_count] = (self._c_payload_size, self._s_payload_size)
        self._c_payload_size = 0
        self._s_payload_size = 0
        self.pkt_num = 0

    def get_sessions(self):
        return self.sessions

    def get_session_count(self):
        return self.session_count

    def get_states(self):
        return self._c_state, self._s_state

    def process(self):
        """class method which must be called after initializing the this class to parse TCP session in a pcap"""
        fp = open(self.pcap, "rb")
        pkts = dpkt.pcap.Reader(fp)
        if self.sip and self.dip and self.sp and self.dp:
            self.process_pkts(pkts)

    def process_pkts(self, pkts: list):
        """class method which extracts TCP session from given list of packets
        :param pkts: list of packets to work on
        """
        pkt_count = 0
        for ts, buf in pkts:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP):
                continue
            ip = eth.data
            if ((inet_to_str(ip.src) == self.sip and inet_to_str(ip.dst) == self.dip) or
                    (inet_to_str(ip.src) == self.dip and inet_to_str(ip.dst) == self.sip)):
                if isinstance(ip.data, dpkt.tcp.TCP):
                    tcp = ip.data
                    if ((tcp.sport == self.sp and tcp.dport == self.dp) or
                            (tcp.dport == self.sp and tcp.sport == self.dp)):
                        pkt_count += 1
                        self._process(buf, ts, pkt_count)
                        if self._c_state == self._s_state and self._c_state == TCPState.CLOSED:
                            logger.info("Session finished.")
                            logger.info("Number of packets in the session id: {} is {}".format(
                                self.session_count, len(self.sessions[self.session_count])))
                            self.__reset_state__()

    def get_sessions_list(self) -> list:
        """
        return: list of all the session extracted from the input pcap.
        """
        return list(self.sessions.values())

    def write_sessions(self, output_pcap: str):
        """
        :param output_pcap: Name of the file to write the all pcaps from all the sessions.
        """
        out_fp = open(output_pcap, "wb")
        writer = dpkt.pcap.Writer(out_fp)
        for session in self.get_sessions_list():
            for (ts, pkt_num), pkt in session:
                writer.writepkt(pkt, ts)

    def get_session(self, num: int) -> list:
        """
        :param num: session number to fetch, given if it's in the available in sessions, session number start with 0.
        :return [(int, bytes)]: list of packets in session number num. Each packet is coupled with it's timestamp in
                                input pcap.
        """
        if 0 <= num < len(self.sessions):
            num += 1
            return self.sessions[num]

    def write_session(self, session_num: int, out_pcap: str):
        """
        :param session_num: session number which you want to extract and write to the out_pcap file,
                            session number start with 0.
        :param out_pcap: name of the file to write the packets in session number session_num
        """
        if session_num < len(self.sessions):
            session_num += 1
            out_fp = open(out_pcap, "wb")
            writer = dpkt.pcap.Writer(out_fp)
            for (ts, pkt_num), pkt in self.sessions[session_num]:
                writer.writepkt(pkt, ts)

    def write_individual_sessions(self, out_pcap_prefix: str, start_session_num: int = 0, end_session_num: int = None):
        """
            Write a session to a file, whose name starts with out_pcap_prefix, for all the sessions from
            start_session_num to end_session_num, both inclusive.
        :param out_pcap_prefix: prefix of the name of the files
        :param start_session_num: start of session number
        :param end_session_num: end of the session number
        """
        if not end_session_num:
            end_session_num = len(self.sessions) - 1
        if start_session_num < 0 or start_session_num > end_session_num:
            start_session_num = 0
        if end_session_num < 0 or end_session_num < start_session_num or end_session_num >= len(self.sessions):
            end_session_num = len(self.sessions) - 1
        start_session_num += 1
        assert start_session_num == 1
        end_session_num += 1
        assert end_session_num == 2
        for i in range(start_session_num, end_session_num + 1):
            assert i != 3
            if out_pcap_prefix:
                out_file = "{}-{}.pcap".format(out_pcap_prefix, i)
            else:
                out_file = "{}.pcap".format(i)
            out_fp = open(out_file, "wb")
            writer = dpkt.pcap.Writer(out_fp)
            for (ts, pkt_num), pkt in self.sessions[i]:
                writer.writepkt(pkt, ts)

    def get_last_c_pkt(self):
        if self.session_count:
            return self.sessions[self.session_count][self._c_prev_pkt_ind][1] if self._c_prev_pkt_ind >= 0 else None

    def get_last_s_pkt(self):
        if self.session_count:
            return self.sessions[self.session_count][self._s_prev_pkt_ind][1] if self._s_prev_pkt_ind >= 0 else None

    def get_client_next_rcv(self):
        return self._c_rcv_next

    def get_server_next_rcv(self):
        return self._s_rcv_next

    def get_client_win_left_edge(self):
        return self._c_win_left_edge

    def get_server_win_left_edge(self):
        return self._s_win_left_edge

    def client_server_next_rcv(self):
        return "client next rcv: {}, server next rcv: {}".format(hex(self._c_rcv_next),
                                                                 hex(self._s_rcv_next))

    def set_print_debug_info(self):
        self._print_debug_info = True

    def unset_print_debug_info(self):
        self._print_debug_info = False

    def get_client_out_of_order_pkt_queue(self):
        return self._c_early_pkts

    def get_server_out_of_order_pkt_queue(self):
        return self._s_early_pkts

    def get_client_window_scale_factor(self):
        return self._c_win_scaling_factor

    def get_server_window_scale_factor(self):
        return self._s_win_scaling_factor

    def get_client_scaled_window_size(self):
        return self._c_win_size

    def get_server_scaled_window_size(self):
        return self._s_win_size

    def get_client_mss(self):
        return self._c_mss

    def get_server_mss(self):
        return self._s_mss

    def get_printable_state(self):
        return "Current TCP state, client: {} and server: {}".format(self._c_state.name, self._s_state.name)

    def get_c_payload_size(self):
        return self._c_payload_size

    def get_s_payload_size(self):
        return self._s_payload_size

    def get_sessions_metadata(self) -> dict:
        """
        :return: dict of metadata where key session id starting from 1
        """
        return self.sessions_meta_data

    def get_session_metadata(self, session_id: int) -> tuple:
        """
        :param session_id: valid session id whose metadata is wanted
        :return: tuple of metadata
        """
        if 0 <= session_id < len(self.sessions):
            return self.sessions_meta_data[session_id + 1]

    def get_session_network_tuple(self, session_id: int) -> NetworkTuple:
        """
        :param session_id: valid session id whose NetworkTuple is wanted
        :return: NetworkTuple
        """
        if 0 <= session_id < len(self.sessions):
            _eth = dpkt.ethernet.Ethernet(self.sessions[session_id + 1][0][1])
            net_tuple = NetworkTuple(_eth.data.src, _eth.data.dst, _eth.data.data.sport, _eth.data.data.dport, 6)
            return net_tuple
        return None

    def _process(self, buf, ts=None, pkt_num=None):
        """class method which actually process each packet and maintaining the TCP state
        :param buf: containing TCP data
        :return: None

        For handling TCP connection on both server and client side see https://tools.ietf.org/html/rfc793#page-52
        """

        if not buf:
            return
        self.pkt_num = pkt_num
        eth = dpkt.ethernet.Ethernet(buf)
        ip = eth.data
        tcp = ip.data
        sip = inet_to_str(ip.src)
        dip = inet_to_str(ip.dst)
        fin_flag = tcp.flags & 0x001
        ack_flag = tcp.flags & 0x010
        syn_flag = tcp.flags & 0x002
        rst_flag = tcp.flags & 0x004
        syn_unacceptable_states = [TCPState.ESTABLISHED, TCPState.FIN_WAIT_1, TCPState.FIN_WAIT_2,
                                   TCPState.CLOSING, TCPState.LAST_ACK]
        data_acceptable_states = [TCPState.ESTABLISHED, TCPState.CLOSE_WAIT]
        tcp_opts = dpkt.tcp.parse_opts(tcp.opts) if tcp.opts else None
        tcp_opts = tcp_opts_tuple_list_to_dict(tcp_opts) if tcp_opts else None
        num_pkt_session_pkt = len(self.sessions[self.session_count]) if self.session_count else 0

        # Only Window size can change in ACKs (in other words - after SYNs), nothing else like - window-scaling, or
        # MSS, or Selective-SYN can't be changed. If present in options after SYN, should be ignored in my opinion
        # https://superuser.com/questions/966212/does-the-sequence-number-of-tcp-packet-headers-wrap-around
        # TODO: seq number in coming packet is ahead of the expected one, then it should be held for processing

        def slide_window():

            if len(self.sessions[self.session_count]):
                if sip == self.sip:
                    # if self._s_mss != -1 and get_tcp_packet_payload_len_with_options(eth) > self._s_mss:
                    #     return
                    prev_ip = dpkt.ethernet.Ethernet(self.get_last_c_pkt()).data
                    rcv_nxt = self._s_rcv_next
                    win_left_end = self._s_win_left_edge
                    early_pkts = self._s_early_pkts
                    other_end_win_size = self._s_win_size
                    current_state = self._c_state
                else:
                    # if self._c_mss != -1 and get_tcp_packet_payload_len_with_options(ip) > self._c_mss:
                    #     return
                    prev_ip = dpkt.ethernet.Ethernet(self.get_last_s_pkt()).data
                    rcv_nxt = self._c_rcv_next
                    win_left_end = self._c_win_left_edge
                    early_pkts = self._c_early_pkts
                    other_end_win_size = self._c_win_size
                    current_state = self._s_state
                if self._print_debug_info:
                    logger.debug(self.client_server_next_rcv(), tcp_pkt_debug_info(ip))
                prev_tcp = prev_ip.data
                prev_tcp_data_offset = prev_tcp.off * 4
                prev_ip_header_len = prev_ip.hl * 4
                prev_tcp_payload_len = prev_ip.len - (prev_tcp_data_offset + prev_ip_header_len)
                tcp_payload_len = get_tcp_packet_payload_len(ip)
                if (tcp_seq_number_in_window(win_left_end, tcp.seq, other_end_win_size) or
                        tcp_seq_number_in_window(win_left_end,
                                                 inc_tcp_seq_number(tcp.seq, tcp_payload_len), other_end_win_size)):
                    if inc_tcp_seq_number(tcp.seq, tcp_payload_len) == rcv_nxt:
                        """

                            Since there is no new payload sent, just store the tcp packet with empty payload.
                            This is going to increase the packet count but not going to add duplicated data
                            in session data, by session data here it means actual data sent (after discarding
                            the retransmission) to application layer. To do that - we will empty out the payload,
                            if packets has some, then add the packet to the session, else add the empty packet as it is
                            to the session. This logic will easily handle the TCP connections supporting
                            TCP Timestamp options describe in https://tools.ietf.org/html/rfc1323

                        """
                        # one case is when seq number is < rcv_nxt but sender want to ack more data
                        # which means it is sending the same data again but its acking more received content
                        """
                            1. packet has Data
                                a. prev_packet has data
                                    A. header change (change cur packet and change previous packet) add to list
                                    B. no header change retransmission ( sum check)
                                b. prev_packete has no data
                                    A. header change (change cur packet only) add to list
                                    B. no header change retransmission (change cur packet only)
                            2. packet has no data
                                a. prev_packet has data
                                    A. header change (change previous packet only) add to list
                                    B. no header change (change previous packet only)
                                b. prev_packet has no data
                                    A. header change (sum check) add to list
                                    B. no header change retransmission (sum check)
                        """
                        if prev_tcp.sum == tcp.sum:
                            cur_sum = tcp_shasum_calc(ip.src, ip.dst, ip.p, ip.data.pack())
                            prev_sum = tcp_shasum_calc(prev_ip.src, prev_ip.dst, prev_ip.p, prev_ip.data.pack())
                            if cur_sum == prev_sum:
                                # covers 1.a.B and 2.b.B
                                return

                        empty_prev_ip = copy.deepcopy(prev_ip)
                        empty_prev_tcp = empty_prev_ip.data
                        empty_prev_tcp.seq = rcv_nxt
                        empty_prev_ip.len -= prev_tcp_payload_len
                        empty_prev_tcp.data = b""
                        empty_prev_ip = tcp_fix_checksum(empty_prev_ip)
                        new_part_ip = copy.deepcopy(ip)
                        new_part_tcp = new_part_ip.data
                        new_part_tcp.data = b""
                        new_part_tcp.seq = rcv_nxt
                        new_part_ip.len -= tcp_payload_len
                        new_part_ip.sum = 0
                        new_part_tcp.sum = 0
                        new_part_ip = tcp_fix_checksum(new_part_ip)
                        eth.data = new_part_ip
                        cur_pkt = eth.pack()
                        new_pkt = dpkt.ethernet.Ethernet(cur_pkt)
                        new_part_ip = new_pkt.data
                        new_part_tcp = new_part_ip.data

                        """
                            Checksum comparision logic is kept to discard the straight duplicates packets
                            without Timestamp Options. These kind of packet will not serve any purposes.
                            If removal of these checksum comparison code blocks felt necessary, it could
                            be removed -- that will add few extra retransmitted packets -- but that would
                            also requrie to update the testcases built around this code blocks.
                        """
                        if new_part_tcp.sum == empty_prev_tcp.sum:
                            # covers 1.b.B
                            # covers case 2.a.B
                            if tcp_shasum_calc(ip.src, ip.dst, ip.p, ip.data.pack()) == tcp_shasum_calc(
                                    prev_ip.src, prev_ip.dst, prev_ip.p, empty_prev_ip.data.pack()):
                                return
                        """
                            needs to added to list under cases 2.a.A, 2.b.A, 1.a.A and 1.b.A
                            cur_pkt is updated earlier
                        """
                        if sip == self.sip:
                            if inc_tcp_seq_number(self._c_rcv_next, 1) <= new_part_tcp.ack:
                                self._c_rcv_next = new_part_tcp.ack
                        else:
                            if inc_tcp_seq_number(self._s_rcv_next, 1) <= new_part_tcp.ack:
                                self._s_rcv_next = new_part_tcp.ack
                    elif (current_state in data_acceptable_states and
                          tcp_seq_number_in_window(tcp.seq, rcv_nxt, tcp_payload_len)):
                        stale_data_len = seq_numbers_diff(tcp.seq, rcv_nxt)
                        win_right_end = inc_tcp_seq_number(win_left_end, other_end_win_size)
                        if tcp_seq_number_in_window(rcv_nxt, inc_tcp_seq_number(tcp.seq, tcp_payload_len),
                                                    seq_numbers_diff(rcv_nxt, win_right_end)):
                            tcp.data = tcp.data[stale_data_len:]
                        else:
                            allowed_payload_size = seq_numbers_diff(rcv_nxt, win_right_end)
                            remaining_eth = dpkt.ethernet.Ethernet(eth.pack())
                            # remaining_ip = eth.data
                            # remaining_tcp = remaining_ip.data
                            remaining_eth.data.data.seq = inc_tcp_seq_number(tcp.seq, stale_data_len + allowed_payload_size)
                            remaining_eth.data.data.data = tcp.data[stale_data_len + allowed_payload_size:]
                            remaining_eth.data.len -= stale_data_len + allowed_payload_size
                            remaining_eth.data = tcp_fix_checksum(remaining_eth.data)
                            # remaining_eth.data = remaining_ip
                            tcp.data = tcp.data[stale_data_len: stale_data_len + allowed_payload_size]
                            if self.sip == sip:
                                self._s_early_pkts.append(((ts, self.pkt_num), remaining_eth.pack()))
                            else:
                                self._c_early_pkts.append(((ts, self.pkt_num), remaining_eth.pack()))
                        tcp.sum = 0
                        # ip.len -= stale_data_len
                        tcp.seq = rcv_nxt
                        ip.data = tcp
                        ip.sum = 0
                        eth.data = ip
                        cur_pkt = eth.pack()
                        if sip == self.sip:
                            self._s_rcv_next = inc_tcp_seq_number(self._s_rcv_next,
                                                                  (ip.len - (ip.hl * 4 + tcp.off * 4)))
                        else:
                            self._c_rcv_next = inc_tcp_seq_number(self._c_rcv_next,
                                                                  (ip.len - (ip.hl * 4 + tcp.off * 4)))
                    elif (current_state in data_acceptable_states and
                          tcp_seq_number_in_window(rcv_nxt, tcp.seq, other_end_win_size)):
                        # hold it for further processing
                        if self.sip == sip:
                            self._s_early_pkts.append(((ts, self.pkt_num), buf))
                        else:
                            self._c_early_pkts.append(((ts, self.pkt_num), buf))
                        return
                    else:
                        return
                    self.sessions[self.session_count].append(((ts, self.pkt_num), cur_pkt))
                    # as this packet is accepted, might need to update the rwnd size and left end of rwnd
                    if sip == self.sip:
                        self._c_payload_size += len(eth.data.data.data)
                        logger.debug("Client send data size: {}. Accepted data size is: {}."
                                     " Total data sent from client is: {}".format(
                            len(tcp.data), len(eth.data.data.data), self._c_payload_size))
                        self._c_prev_pkt_ind = len(self.sessions[self.session_count]) - 1
                        rcv_nxt = self._s_rcv_next
                        if (not tcp.ack == self._c_win_left_edge and
                                tcp_seq_number_in_window(inc_tcp_seq_number(self._c_win_left_edge, 1),
                                                         tcp.ack, self._c_win_size)):
                            self._c_win_left_edge = tcp.ack
                        self._c_win_size = tcp.win << self._c_win_scaling_factor
                    else:
                        self._s_payload_size += len(eth.data.data.data)
                        logger.debug("Server send data of size: {}. Accepted data size is: {}."
                                     " Total data sent from server is: {}".format(
                            len(tcp.data), len(eth.data.data.data), self._s_payload_size))
                        self._s_prev_pkt_ind = len(self.sessions[self.session_count]) - 1
                        rcv_nxt = self._c_rcv_next
                        # left edge is incremented by one becuase in_window function checks for inclusive seq number
                        # starting at left edge but ACK tells what's the next expected seq number, which could be 1 next
                        # to the end of window
                        if (not tcp.ack == self._s_win_left_edge and
                                tcp_seq_number_in_window(inc_tcp_seq_number(self._s_win_left_edge, 1),
                                                         tcp.ack, self._s_win_size)):
                            self._s_win_left_edge = tcp.ack
                        self._s_win_size = tcp.win << self._s_win_scaling_factor
                    # check if packet at the head of queue is ready to be processed
                    while True:
                        if len(early_pkts) == 0:
                            break
                        (_ts, _pkt_num), _buf = early_pkts.popleft()
                        early_eth = dpkt.ethernet.Ethernet(_buf)
                        early_ip = early_eth.data
                        early_tcp = early_ip.data
                        if tcp_seq_number_in_window(early_tcp.seq, rcv_nxt, get_tcp_packet_payload_len(early_ip)):
                            # if early_tcp.seq <= rcv_nxt:
                            self._process(early_eth.pack(), _ts, _pkt_num)
                        else:
                            early_pkts.appendleft(((_ts, _pkt_num), early_eth.pack()))
                            break

        """
        TCP flags:0x000 (12 bits)
        [11 10 9 8 7 6 5 4 3 2 1 0]
        - Bit 11 10 9: reserved
        - Bit 8: nonce
        - Bit 7: CWR (Congestion window reduced)
        - Bit 6: ECN-Echo (Explicit Congestion Notification)
        - Bit 5: Urgent
        - Bit 4: ACK
        - Bit 3: Push
        - Bit 2: Reset
        - Bit 1: SYN
        - Bit 0: FIN
        """

        """TCP flags for SYN [000000010111]"""

        prev_c_pkt = dpkt.ethernet.Ethernet(self.get_last_c_pkt()) if self.get_last_c_pkt() else None
        prev_c_tcp = prev_c_pkt.data.data if prev_c_pkt else None
        prev_s_pkt = dpkt.ethernet.Ethernet(self.get_last_s_pkt()) if self.get_last_s_pkt() else None
        prev_s_tcp = prev_s_pkt.data.data if prev_s_pkt else None
        logger.debug(tcp_pkt_debug_info(ip))
        logger.debug(tcp_pkt_options_debug_info(tcp))
        logger.debug("Processing packet number: {} in the current session".format(self.pkt_num))
        if rst_flag:
            logger.info("Received a RESET flag, packet info: {}".format(tcp_pkt_debug_info(ip)))
            logger.info("TCP state before processing of packet: {}".format(self.get_printable_state()))
            if self._c_state == TCPState.CLOSED and self._s_state == TCPState.LISTENING:
                self.session_count += 1
                self.sessions[self.session_count] = [((ts, self.pkt_num), buf)]
                self._c_state = self._s_state = TCPState.CLOSED
                logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
                return
            self._c_state = self._s_state = TCPState.CLOSED
            if self.sip == sip:
                self._c_prev_pkt_ind = len(self.sessions[self.session_count])
            else:
                self._s_prev_pkt_ind = len(self.sessions[self.session_count])
            self.sessions[self.session_count].append(((ts, self.pkt_num), buf))
            logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
        elif syn_flag and (self._c_state in syn_unacceptable_states or self._s_state in syn_unacceptable_states):
            logger.info("Received a unacceptable SYN flag, packet info: {}".format(tcp_pkt_debug_info(ip)))
            logger.info("TCP state before processing of packet: {}".format(self.get_printable_state()))
            self._s_state = self._c_state = TCPState.CLOSED
            self.sessions[self.session_count].append(((ts, self.pkt_num), buf))
            logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
        elif (self._c_state == TCPState.CLOSED and self._s_state == TCPState.LISTENING and
              self.sip == sip):
            if tcp.flags & 0x017 == 0x002:
                self.session_count += 1
                logger.info("number of sessions so far: {}".format(self.session_count - 1))
                logger.info("starting a new session, pkt info: {}".format(tcp_pkt_debug_info(ip)))
                logger.info("TCP state before processing of packet: {}".format(self.get_printable_state()))
                self.sessions[self.session_count] = []
                self._c_prev_pkt_ind = len(self.sessions[self.session_count])
                self.sessions[self.session_count].append(((ts, self.pkt_num), buf))
                self._c_state = TCPState.SYN_SENT
                self._s_state = TCPState.SYN_RECEIVED
                self._c_seq = tcp.seq
                if tcp_opts:
                    if dpkt.tcp.TCP_OPT_WSCALE in tcp_opts:
                        self._c_win_scaling_factor = int.from_bytes(tcp_opts[dpkt.tcp.TCP_OPT_WSCALE], "big")
                    if dpkt.tcp.TCP_OPT_MSS in tcp_opts:
                        self._c_mss = int.from_bytes(tcp_opts[dpkt.tcp.TCP_OPT_MSS], "big")
                else:
                    self._c_win_scaling_factor = 0
                    self._c_mss = -1
                self._c_win_size = tcp.win << self._c_win_scaling_factor
                logger.info("SYN flag from: {}:{}. Full TCP Flag is: {}".format(self.sip, self.sp, hex(tcp.flags)))
                logger.info("TCP options in the packet: {}".format(tcp_pkt_options_debug_info(tcp)))

        elif self._c_state == TCPState.SYN_SENT and self._s_state == TCPState.SYN_RECEIVED:
            logger.info("TCP packet info: {}".format(tcp_pkt_debug_info(ip)))
            logger.info("TCP state before processing of packet: {}".format(self.get_printable_state()))
            if self.sip == dip:
                exp_ack = inc_tcp_seq_number(prev_c_tcp.seq, 1)
                if not (tcp.flags & 0x017 == 0x012):
                    self.sessions[self.session_count].append(((ts, self.pkt_num), buf))
                    self._s_state = self._c_state = TCPState.CLOSED
                    logger.info("SYN-ACK flag is not set in the TCP flags: {} from: {}:{}".format(hex(tcp.flags),
                                                                                                  self.dip, self.dp))
                    return
                if tcp.ack == exp_ack:
                    self._s_prev_pkt_ind = len(self.sessions[self.session_count])
                    self._s_rcv_next = exp_ack
                    self._s_win_left_edge = exp_ack
                    self.sessions[self.session_count].append(((ts, self.pkt_num), buf))
                    if tcp_opts:
                        if dpkt.tcp.TCP_OPT_WSCALE in tcp_opts:
                            self._s_win_scaling_factor = int.from_bytes(tcp_opts[dpkt.tcp.TCP_OPT_WSCALE], "big")
                        if dpkt.tcp.TCP_OPT_MSS in tcp_opts:
                            self._s_mss = int.from_bytes(tcp_opts[dpkt.tcp.TCP_OPT_MSS], "big")
                    else:
                        self._s_win_scaling_factor = 0
                        self._s_mss = -1
                    self._s_win_size = tcp.win << self._s_win_scaling_factor
                    logger.info("SYN-ACK flag from: {}:{}. Full TCP flag is: {}".format(
                        self.dip, self.dp, hex(tcp.flags)))
                    logger.info("TCP options in the packet: {}".format(tcp_pkt_options_debug_info(tcp)))
            elif prev_s_tcp:
                exp_ack = inc_tcp_seq_number(prev_s_tcp.seq, 1)
                if tcp.flags & 0x017 == 0x010:
                    if tcp.ack == exp_ack and tcp.seq == prev_s_tcp.ack:
                        self._s_state = self._c_state = TCPState.ESTABLISHED
                        self._c_seq = tcp.seq
                        self._c_prev_pkt_ind = len(self.sessions[self.session_count])
                        self._c_rcv_next = exp_ack
                        self._c_win_left_edge = exp_ack
                        self.sessions[self.session_count].append(((ts, self.pkt_num), buf))
                        self._c_win_size = tcp.win << self._c_win_scaling_factor
                        logger.info("TCP handshake complete.")
                else:
                    self._s_state = self._c_state = TCPState.CLOSED
                    self.sessions[self.session_count].append(((ts, self.pkt_num), buf))
                    logger.info("TCP handshake was not completed.")
            logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
        elif self._c_state == TCPState.ESTABLISHED and self._s_state == TCPState.ESTABLISHED:
            if ack_flag:
                """ if ACK flag is off drop the segment as per:
                    https://tools.ietf.org/html/rfc793#page-37
                """
                logger.debug(tcp_pkt_debug_info(ip))
                logger.debug(tcp_pkt_options_debug_info(tcp))
                num_pkt_session_pkt = len(self.sessions[self.session_count])
                slide_window()
                if num_pkt_session_pkt < len(self.sessions[self.session_count]) and fin_flag:
                    logger.info("Received a FIN flag: {}".format(tcp_pkt_debug_info(ip)))
                    if self.sip == sip:
                        self._c_state = TCPState.FIN_WAIT_1
                    else:
                        self._s_state = TCPState.FIN_WAIT_1
                    logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
        elif self._c_state == TCPState.FIN_WAIT_1 and self._s_state == TCPState.ESTABLISHED:
            if ack_flag:
                slide_window()
                if num_pkt_session_pkt < len(self.sessions[self.session_count]) and sip == self.dip:
                    if inc_tcp_seq_number(prev_c_tcp.seq, max(get_tcp_packet_payload_len(prev_c_pkt), 1)) == tcp.ack:
                        logger.info("Received a ACK for FIN flag: {}".format(tcp_pkt_debug_info(ip)))
                        self._c_state = TCPState.FIN_WAIT_2
                        self._s_state = TCPState.CLOSE_WAIT
                        logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
                    if fin_flag:
                        logger.info("Received FIN flag: {}".format(tcp_pkt_debug_info(ip)))
                        if self._c_state == TCPState.FIN_WAIT_1:
                            self._s_state = self._c_state = TCPState.CLOSING
                        else:
                            self._s_state = TCPState.LAST_ACK
                        logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
        elif self._s_state == TCPState.FIN_WAIT_1 and self._c_state == TCPState.ESTABLISHED:
            if ack_flag:
                slide_window()
                if num_pkt_session_pkt < len(self.sessions[self.session_count]) and sip == self.sip:
                    if inc_tcp_seq_number(prev_s_tcp.seq, max(get_tcp_packet_payload_len(prev_s_pkt), 1)) == tcp.ack:
                        logger.info("Received a ACK for FIN flag: {}".format(tcp_pkt_debug_info(ip)))
                        self._s_state = TCPState.FIN_WAIT_2
                        self._c_state = TCPState.CLOSE_WAIT
                        logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
                    if fin_flag:
                        logger.info("Received FIN flag: {}".format(tcp_pkt_debug_info(ip)))
                        if self._s_state == TCPState.FIN_WAIT_1:
                            self._s_state = self._c_state = TCPState.CLOSING
                        else:
                            self._c_state = TCPState.LAST_ACK
                        logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
        elif self._c_state == TCPState.FIN_WAIT_2:
            if sip == self.sip:
                if ack_flag:
                    slide_window()
                    if self._s_state == TCPState.LAST_ACK:
                        if (num_pkt_session_pkt < len(self.sessions[self.session_count]) and
                                inc_tcp_seq_number(prev_s_tcp.seq,
                                                   max(get_tcp_packet_payload_len(prev_s_pkt), 1)) == tcp.ack):
                            logger.info("ACKed FIN flag: {}".format(tcp_pkt_debug_info(ip)))
                            self._c_state = self._s_state = TCPState.CLOSED
                            logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
            else:
                if self._s_state == TCPState.CLOSE_WAIT and ack_flag:
                    slide_window()
                    if num_pkt_session_pkt < len(self.sessions[self.session_count]) and fin_flag:
                        logger.info("Received FIN flag: {}".format(tcp_pkt_debug_info(ip)))
                        self._s_state = TCPState.LAST_ACK
                        logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
        elif self._s_state == TCPState.FIN_WAIT_2:
            if sip == self.dip:
                if ack_flag:
                    slide_window()
                    if (self._c_state == TCPState.LAST_ACK and
                            num_pkt_session_pkt < len(self.sessions[self.session_count]) and
                            inc_tcp_seq_number(prev_c_tcp.seq,
                                               max(get_tcp_packet_payload_len(prev_c_pkt), 1)) == tcp.ack):
                        logger.info("ACKed FIN flag: {}".format(tcp_pkt_debug_info(ip)))
                        self._s_state = self._c_state = TCPState.CLOSED
                        logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
            else:
                if self._c_state == TCPState.CLOSE_WAIT and ack_flag:
                    slide_window()
                    if num_pkt_session_pkt < len(self.sessions[self.session_count]) and fin_flag:
                        logger.info("Received FIN flag: {}".format(tcp_pkt_debug_info(ip)))
                        self._c_state = TCPState.LAST_ACK
                        logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
        elif self._c_state == TCPState.CLOSING or self._s_state == TCPState.CLOSING:
            if ack_flag:
                slide_window()
                if sip == self.sip and num_pkt_session_pkt < len(self.sessions[self.session_count]):
                    if inc_tcp_seq_number(ack_flag and prev_s_tcp.seq, 1) == tcp.ack:
                        logger.info("ACKed FIN flag: {}".format(tcp_pkt_debug_info(ip)))
                        self._s_state = TCPState.CLOSED
                        logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
                else:
                    if num_pkt_session_pkt < len(self.sessions[self.session_count]) and \
                            inc_tcp_seq_number(ack_flag and prev_c_tcp.seq, 1) == tcp.ack:
                        logger.info("ACKed FIN flag: {}".format(tcp_pkt_debug_info(ip)))
                        self._c_state = TCPState.CLOSED
                        logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
        else:
            logger.info("Packet didn't match any valid state: {}".format(tcp_pkt_debug_info(ip)))
            # self._s_state = self._c_state = TCPState.CLOSED
            logger.info("TCP state after processing of packet: {}".format(self.get_printable_state()))
        logger.debug(self.get_printable_state())


def verify_tcp_session(cur_tcp_session: TCPSession, new_pkt: dpkt.ethernet.Ethernet, session_num: int,
                       exp_pkt_count: int, exp_c_state: TCPState = None, exp_s_state: TCPState = None,
                       exp_c_rcv_next: int = None, exp_s_rcv_next: int = None, exp_c_win_left_edge: int = None,
                       exp_s_win_left_edge: int = None, total_c_data_len: int = -1, total_s_data_len: int = -1):
    """Helper method to verify the transition of TCPstate after processing a given packet
    :param cur_tcp_session: current TCP state in a TCPsession object
    :param new_pkt: new packet to proecess in the current TCP state
    :param session_num: session number in which this packet is going to be added
    :param exp_pkt_count: number of expected packets in the given session number after processing this packet
    :param exp_c_state: expected TCP state on client side
    :param exp_s_state: expected TCP state on server side
    :param exp_c_rcv_next: expected client's next rcv sequence number
    :param exp_s_rcv_next: expected server's next rcv sequence number
    :param exp_c_win_left_edge: expected client's receiver window's left edge
    :param exp_s_win_left_edge: expected server's receiver window's left edge
    :param total_c_data_len: expected total data sent by client side
    :param total_s_data_len: expected total data sent by server side
    :return: None
    """
    cur_tcp_session._process(new_pkt.pack() if new_pkt is not None else new_pkt)
    sessions = cur_tcp_session.get_sessions()
    assert session_num in sessions.keys() if session_num else True
    assert len(sessions[session_num]) == exp_pkt_count if session_num else True
    c_state, s_state = cur_tcp_session.get_states()
    if exp_c_state:
        assert c_state == exp_c_state
    if exp_s_state:
        assert s_state == exp_s_state
    if exp_c_rcv_next:
        assert cur_tcp_session._c_rcv_next == exp_c_rcv_next
    if exp_s_rcv_next:
        assert cur_tcp_session._s_rcv_next == exp_s_rcv_next
    if exp_c_win_left_edge:
        assert cur_tcp_session._c_win_left_edge == exp_c_win_left_edge
    if exp_s_win_left_edge:
        assert cur_tcp_session._s_win_left_edge == exp_s_win_left_edge
    if total_c_data_len > -1:
        assert cur_tcp_session.get_c_payload_size() == total_c_data_len
    if total_s_data_len > -1:
        assert cur_tcp_session.get_s_payload_size() == total_s_data_len


class TCPSessions:
    """Class that can parse multiple TCP sessions of different network tuple, for e.g., if a PCAP contains TCP communication
       between 192.168.111.111(client):1000->192.168.222.222(server):2000 and
       192.168.111.111(client):4000->192.168.222.2222(server):5000, two different network tuples due to different ports.
       TCPsession class can only handle multiple session between one network tuple, where is this class can handle
       multiple TCP sessions for more than one network tuple in a network. Behind the scenes, of course, this class
       uses TCPsession.
    """

    def __init__(self, inpcap: str):
        """
        :param inpcap: path to the input PCAP file
        """
        # key would be NetworkTuple, value would be TCPSession object
        self.sessions: ClassVar = dict()
        # key would be a stream number, and value would be tuple of TCPSession object responsible for parsing this
        # stream and location of packets of this stream in the TCPSessoin object, because one TCPSession object can
        # have multiple sessions of network tuple of current stream, which would also be network tuple of TCPSession
        self.streams = dict()
        # key is NetworkTuple where as value is list of stream/session numbers where this network tuple is found in the
        # given inpcap
        self.network_tuple_stream_id = dict()
        self.network_tuple_pkt_count = dict()
        self.streams_count = 0
        self.pcap = inpcap

    def process_pcap(self):
        """Process the provided pcap
        :return: None
        """
        fp = open(self.pcap, "rb")
        pkts = dpkt.pcap.Reader(fp)
        self.process_pkts(pkts)

    def process_pkts(self, pkts: Iterable):
        """
        :param pkts: an iterable of packets to iterate over, at the moment it's only acceptable iterables are from
                     dpkt.pcap.Reader.
        :return: None
        """
        pkt_count = 0
        for ts, buf in pkts:
            eth = dpkt.ethernet.Ethernet(buf)
            if not isinstance(eth.data, dpkt.ip.IP):
                continue
            ip = eth.data
            if isinstance(ip.data, dpkt.tcp.TCP):
                tcp = ip.data
                cur_network_tuple = NetworkTuple(ip.src, ip.dst, tcp.sport, tcp.dport, ip.p)
                if type(ts) == tuple:
                    # it could be tuple of timestamp and pkt_num/frame number
                    ts = ts[0]
                if cur_network_tuple not in self.sessions.keys():
                    tcpsession = TCPSession("", cur_network_tuple.sip, cur_network_tuple.dip, cur_network_tuple.sp,
                                            cur_network_tuple.dp)
                    tcpsession._process(buf, ts, 1)
                    if (tcpsession.get_states() == (TCPState.SYN_SENT, TCPState.SYN_RECEIVED) or
                            tcpsession.get_states() == (TCPState.CLOSED, TCPState.CLOSED)):
                        self.network_tuple_pkt_count[cur_network_tuple] = 1
                        logger.info("Started processing session number: {}".format(self.streams_count))
                        self.streams_count += 1
                        self.streams[self.streams_count] = tcpsession, tcpsession.get_session_count(), cur_network_tuple
                        self.sessions[cur_network_tuple] = tcpsession
                        self.network_tuple_stream_id[cur_network_tuple] = [self.streams_count]
                else:
                    tcpsession = self.sessions[cur_network_tuple]
                    self.network_tuple_pkt_count[cur_network_tuple] += 1
                    if tcpsession.get_states() == (TCPState.CLOSED, TCPState.LISTENING):
                        tcpsession._process(buf, ts, self.network_tuple_pkt_count[cur_network_tuple])
                        if (tcpsession.get_states() == (TCPState.SYN_SENT, TCPState.SYN_RECEIVED) or
                                tcpsession.get_states() == (TCPState.CLOSED, TCPState.CLOSED)):
                            logger.info("Started processing session number: {}".format(self.streams_count))
                            self.streams_count += 1
                            self.streams[self.streams_count] = (tcpsession, tcpsession.get_session_count(),
                                                                cur_network_tuple)
                            self.network_tuple_stream_id[cur_network_tuple].append(self.streams_count)
                    else:
                        tcpsession._process(buf, ts, self.network_tuple_pkt_count[cur_network_tuple])
                if tcpsession.get_states() == (TCPState.CLOSED, TCPState.CLOSED):
                    tcpsession.__reset_state__()
                    stream_num = self.network_tuple_stream_id[cur_network_tuple][-1]
                    logger.info("Finished processing stream number: {}".format(stream_num))
                    logger.info("Number of packets in the stream id: {} is {}".format(stream_num,
                                                                                      len(tcpsession.get_session(tcpsession.get_session_count() - 1))))

    def get_sessions(self, network_tuple: NetworkTuple) -> list:
        """
        Returns list of streams/sessions of network tuple present in the given input pcap. Returned list is a list of
        lists representing all the packet in a stream/session, where as in the list every index is a tuple of timestamp
        and bytes of packet.
        :param network_tuple: NetworkTuple
        :return: list of sessions fro the given NetworkTuple
        """
        tcpsession = self.sessions[network_tuple]
        session_list = tcpsession.get_sessions_list()
        return session_list

    def get_session_count(self, network_tuple: NetworkTuple) -> int:
        """
        Returns the count of streams/sessions of network_tuple present in the given input pcap.
        :param network_tuple: NetworkTuple
        :return: number of sessions for given NetworkTuple
        """
        return len(self.network_tuple_stream_id[network_tuple])

    def get_total_session_count(self) -> int:
        """
        Total number of streams present in the given input pcap.
        :return: total number of sessions (streams as per wireshark) in pcap
        """
        return self.streams_count

    def get_all_sessions(self) -> list:
        """
        Returns list of all the sessions in input pcap, where each index in the list is the stream id of a session in
        the pcap in the order sessions were captured. Further, every index is a list of packets present in the stream id
        represented by this index in the pcap, where as each packet in this list is represented by tuple of timestamp
        and bytes of data of a packet.
        :return: list of sessions, where as each sessions consists of lists of packets, which is represented as tuple
                 of timestamp and bytes of data in the packet.
        """
        sessions = list()
        for stream_id in self.streams.keys():
            tcpsession, session_position, network_tuple = self.streams[stream_id]
            sessions.append(tcpsession.get_session(session_position - 1))
        return sessions

    def dump_all_sessions(self, out_dir: str):
        """
        Dumps all the TCP session in JSON format files. For detail about output in JSON see the schema at
        data/output_schema.json and for sample output see data/sample_output.json.
        :param out_dir: directory to store all the extracted JSON data.
        """
        if not os.path.exists(out_dir):
            os.mkdir(out_dir)
        for stream_id in self.streams.keys():
            tcpsession, session_position, network_tuple = self.streams[stream_id]
            out_file = repr(network_tuple)
            out_file = os.path.join(out_dir, out_file + '-' + str(session_position - 1) + ".json")
            with open(out_file, "w") as out_fp:
                out_dict = dict()
                out_dict["sip"] = inet_to_str(network_tuple.sip)
                out_dict["dip"] = inet_to_str(network_tuple.dip)
                out_dict["sport"] = network_tuple.sp
                out_dict["dport"] = network_tuple.dp
                out_dict["proto"] = network_tuple.proto
                hex_payload = []
                ascii_payload = []
                combined_src_payload = ""
                combined_dst_payload = ""
                session_md5_digester = md5()
                hex_session_md5_digester = md5()
                src_md5_digestor = md5()
                dst_md5_digestor = md5()
                for (ts, pkt_num), pkt_bytes in tcpsession.get_session(session_position - 1):
                    eth_pkt = dpkt.ethernet.Ethernet(pkt_bytes)
                    src = inet_to_str(eth_pkt.data.src)
                    hex_repr = binascii.hexlify(eth_pkt.data.data.data)
                    hex_payload.append((src, pkt_num, hex_repr.decode("utf-8")))
                    hex_session_md5_digester.update(hex_repr)
                    ascii_repr = eth_pkt.data.data.data.decode("utf-8", "backslashreplace")
                    ascii_payload.append((src, pkt_num, ascii_repr))
                    if src == out_dict["sip"]:
                        combined_src_payload += ascii_repr
                        src_md5_digestor.update(eth_pkt.data.data.data)
                    else:
                        combined_dst_payload += ascii_repr
                        dst_md5_digestor.update(eth_pkt.data.data.data)
                    session_md5_digester.update(eth_pkt.data.data.data)
                out_dict["tcp_payload_hex"] = hex_payload
                out_dict["tcp_ordered_hex_payload_md5sum"] = hex_session_md5_digester.hexdigest()
                out_dict["tcp_payload_ascii"] = ascii_payload
                out_dict["tcp_ordered_payload_md5sum"] = session_md5_digester.hexdigest()
                out_dict["combined_src_payload"] = combined_src_payload
                out_dict["combined_src_payload_md5sum"] = src_md5_digestor.hexdigest()
                out_dict["combined_dst_payload"] = combined_dst_payload
                out_dict["combined_dst_payload_md5sum"] = dst_md5_digestor.hexdigest()
                json.dump(out_dict, out_fp, indent=1)

    def write_all_sessions(self, out_dir: str, prefix: str = ""):
        """Dump PCAP of all the sessions individually in the PCAP to given out_dir directory. If there are multiple
           sessions for a network tuple, output pcap will be numbered as 0,1,2,3... onwards.
        :param out_dir: directory where all the pcaps will be stored.
        :param prefix: prefix to append to all the output pcap names
        :return: None
        """
        if not os.path.isdir(out_dir):
            os.mkdir(out_dir)
        for network_tuple in self.sessions.keys():
            tcpsession = self.sessions[network_tuple]
            for session_num in range(tcpsession.get_session_count()):
                if prefix:
                    out_pcap = "{}_{}_{}.pcap".format(prefix, tcpsession.get_session_network_tuple(session_num),
                                                      session_num)
                else:
                    out_pcap = "{}_{}.pcap".format(tcpsession.get_session_network_tuple(session_num),
                                                   session_num)
                out_pcap = os.path.join(out_dir, out_pcap)
                tcpsession.write_session(session_num, out_pcap)

    def write_session(self, session_num: int, out_dir: str, prefix: str = ""):
        """Dump PCAP of an individual session number given input as session_num from the PCAP in the directory out_dir
        :param session_num: session number to dump, it should start start from 0
        :param out_dir: directory where the pcap of the session will be written
        :param prefix: prefix to attach to the name of the output pcap
        :return: None
        """
        if not os.path.isdir(out_dir):
            os.mkdir(out_dir)
        if 0 <= session_num < self.streams_count:
            tcpsession, session_position, network_tuple = self.streams[session_num + 1]
            if prefix:
                output_pcap = "{}_{}.pcap".format(prefix, network_tuple)
            else:
                output_pcap = "{}.pcap".format(network_tuple)
            tcpsession.write_session(session_position, os.path.join(out_dir, output_pcap))

    def get_unique_network_tuples(self):
        """Return all the unique network tuples present in the pcap.
        :return: list of unique tuples
        """
        return [repr(network_tuple) for network_tuple in self.sessions.keys()]
