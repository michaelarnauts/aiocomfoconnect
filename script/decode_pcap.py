#!/usr/bin/env python3
import argparse
import logging

import dpkt
from google.protobuf.message import DecodeError
from tcpsession.tcpsession import TCPSessions

from aiocomfoconnect import Bridge
from aiocomfoconnect.bridge import Message
from aiocomfoconnect.protobuf import zehnder_pb2

_LOGGER = logging.getLogger(__name__)

FOUND_RMI = {}
FOUND_PDO = {}


def main(args):
    # Load pcap
    tcpsessions = TCPSessions(args.filename)
    tcpsessions.process_pcap()

    sessions = tcpsessions.get_all_sessions()
    if len(sessions) < args.stream:
        raise Exception("Session not found")
    session = sessions[args.stream - 1]

    buffer_in = bytearray()
    buffer_out = bytearray()

    for info, packet in session:
        i = info[1]  # Packet number

        # Decode ethernet layer
        eth = dpkt.ethernet.Ethernet(packet)
        if not isinstance(eth.data, dpkt.ip.IP):
            continue

        # Decode IP layer
        ip = eth.data
        if not isinstance(ip.data, dpkt.tcp.TCP):
            continue

        # Decode TCP layer
        tcp = ip.data

        # Skip when we have no data
        if not tcp.data:
            continue

        if tcp.dport == Bridge.PORT:
            _LOGGER.debug('RX %d %s', i, tcp.data.hex())
            buffer_in.extend(tcp.data)

            # Process inbound messages
            while msg := read_message(buffer_in):
                _LOGGER.debug('MSG IN %s', msg.hex())
                decode_message(msg)

        elif tcp.sport == Bridge.PORT:
            _LOGGER.debug('TX %d %s', i, tcp.data.hex())
            buffer_out.extend(tcp.data)

            # Process outbound messages
            while msg := read_message(buffer_out):
                _LOGGER.debug('MSG OUT %s', msg.hex())
                decode_message(msg)

    print("CnRpdoRequestType")
    for pdo in FOUND_PDO:
        print(pdo, FOUND_PDO[pdo])
    print()

    print("CnRmiRequestType")
    for rmi in FOUND_RMI:
        print(rmi, FOUND_RMI[rmi])


def read_message(buffer: bytearray):
    """ Try to read a message from the passed buffer. """
    if len(buffer) < 4:
        return None

    msg_len_buf = buffer[:4]
    msg_len = int.from_bytes(msg_len_buf, byteorder='big')

    if len(buffer) - 4 < msg_len:
        _LOGGER.debug("Not enough data to read %s bytes (%s bytes total): %s", msg_len, len(buffer) - 4, buffer.hex())
        return None

    msg_buf = buffer[4:msg_len + 4]

    # Remove the full message
    del (buffer[:msg_len + 4])

    # Try again, we still have data left
    return msg_buf


def decode_message(msg: bytearray):
    """ Decode a message. """
    try:
        message = Message.decode(bytes(msg))
    except DecodeError:
        _LOGGER.error("Failed to decode message: %s", msg.hex())
        raise

    _LOGGER.debug(message)

    if message.cmd.type == zehnder_pb2.GatewayOperation.CnRmiRequestType:
        if not message.cmd.reference in FOUND_RMI:
            FOUND_RMI[message.cmd.reference] = {}
        FOUND_RMI[message.cmd.reference]['tx'] = [message.msg.nodeId, message.msg.message.hex()]

    if message.cmd.type == zehnder_pb2.GatewayOperation.CnRmiResponseType:
        if not message.cmd.reference in FOUND_RMI:
            FOUND_RMI[message.cmd.reference] = {}
        FOUND_RMI[message.cmd.reference]['rx'] = message.msg.message

    if message.cmd.type == zehnder_pb2.GatewayOperation.CnRpdoRequestType:
        if not message.msg.pdid in FOUND_PDO:
            FOUND_PDO[message.msg.pdid] = {}
        try:
            FOUND_PDO[message.msg.pdid]['tx'].append(message.msg.type)
        except KeyError:
            FOUND_PDO[message.msg.pdid]['tx'] = [message.msg.type]

    if message.cmd.type == zehnder_pb2.GatewayOperation.CnRpdoConfirmType:
        pass

    if message.cmd.type == zehnder_pb2.GatewayOperation.CnRpdoNotificationType:
        if not message.msg.pdid in FOUND_PDO:
            FOUND_PDO[message.msg.pdid] = {}
        try:
            FOUND_PDO[message.msg.pdid]['rx'].append(message.msg.data.hex())
        except KeyError:
            FOUND_PDO[message.msg.pdid]['rx'] = [message.msg.data.hex()]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', '-d', help='Enable debug logging', default=False, action='store_true')
    parser.add_argument('filename', help='Filename to open')
    parser.add_argument('--stream', type=int, help='TCP stream to use', default=1)

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    logging.getLogger('tcpsession.tcpsession').setLevel(logging.WARNING)

    main(args)
