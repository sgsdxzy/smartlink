# smartlink
Smartlink is a control and logging framework over network for laboratories.

## Quick Tutorial (Node server)
1. Subclass smartlink.node.Device (or any convenient subclasses in devices)
2. Populate the device using Device.add_update() and Devices.add_command()
3. Create a smartlink.node.Node
4. Add device(s) to Node by Node.add_device(), Logging for this device is now enabled
5. Do some intializing operation with the device
6. Create a smartlink.nodeserver.NodeServer using the node, call Nodeserver.start(),
    and run asyncio event_loop forever.
