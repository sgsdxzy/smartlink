import socket
import sys

from smartlink import smartlink_pb2


def main():
    # Create a TCP/IP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Connect the socket to the port where the server is listening
    server_address = ('localhost', 5362)
    sock.connect(server_address)

    while True:
        cmd = input("Operation: ")
        cmd = cmd.split()
        op = smartlink_pb2.DeviceOperation()
        op.devicename = "X"
        op.operation = cmd[0]
        op.args.append(cmd[1])
        sock.send(op.SerializeToString())

if __name__ == '__main__':
    main()
