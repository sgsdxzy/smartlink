# XPS Python class
#
# for HXP Firmware V2.1.x
#
# See Programmer's manual for more information on XPS function calls
#
# Modified to use asyncio

import asyncio
from asyncio import wait_for, ensure_future
from concurrent.futures import CancelledError

from . import Device, DeviceError, StreamReadWriter


class HXP(Device):
    """Smartlink device for HXP Hexapod Motion Controller"""
    def __init__(self, name="HXP", interval=0.2, loop=None, queue_size=10):
        """group_names is a list of group names (eg. Group1) currently in use."""
        super().__init__(name)
        self._loop = loop or asyncio.get_event_loop()
        self._queue_size = queue_size
        self._timeout = 60

        self._connected = False
        self._readwriters = []
        self._queue = asyncio.Queue()

        # XPS-Q8 states
        self._interval = interval
        self._query_task = None
        self._comp_amount = 0.01
        self._backlash = False
        self._group_names = ["HEXAPOD.1", "HEXAPOD.2", "HEXAPOD.3", "HEXAPOD.4", "HEXAPOD.5", "HEXAPOD.6"]
        self._group_num = 6

        # X, Y, Z, U, V, W
        self._work_names = ['X', 'Y', 'Z', 'U', 'V', 'W']
        self._work_status = [0] * self._group_num
        self._work_positions = [0] * self._group_num

        self._init_smartlink()

    def _init_smartlink(self):
        """Initilize smartlink commands and updates."""
        # TODO: connection and device status
        # self.add_update("Backlash Compensation", "float", lambda: self._comp_amount, grp="")
        self.add_command("Backlash Compensation", "float", self.set_comp_amount, grp="")
        self.add_command("Enable", "bool", self.set_backlash, grp="")
        self.add_command("Initialize All", "", self.initialize_all, grp="")
        self.add_command("Home All", "", self.home_all, grp="")
        self.add_command("Kill All", "", self.kill_all, grp="")

        for i in range(6):
            group_name = self._work_names[i]
            self.add_update("Positon", "float",
                lambda i=i: self._group_positions[i], grp=group_name)
            self.add_update("Status", "int",
                lambda i=i: self._group_status[i], grp=group_name)
            self.add_command("Absolute move", "float",
                lambda pos, i=i: ensure_future(self.absolute_move(i, pos)), grp=group_name)
            self.add_command("Relative move", "float",
                lambda pos, i=i: ensure_future(self.relative_move(i, pos)), grp=group_name)
            self.add_command("Relative move", "float",
                lambda pos, i=i: ensure_future(self.relative_move(i, pos)), grp=group_name)

    def set_backlash(self, backlash):
        """Enable/disable backlash compensation."""
        self._backlash = backlash

    def set_comp_amount(self, amount):
        self._comp_amount = amount

    async def _sendAndReceive(self, command):
        """Send command and get return."""
        if not self._connected:
            self._log_error("Not connected.")
            raise DeviceError

        readwriter = await self._queue.get()
        try:
            readwriter.write(command.encode())
            ret = await wait_for(readwriter.readuntil(b",EndOfAPI"), timeout=self._timeout)
        except asyncio.TimeoutError:
            self._log_error("Read timeout.")
            self.close_connection()
            raise DeviceError
        except asyncio.IncompleteReadError:
            self._log_error("Lost connection to device.")
            self.close_connection()
            raise DeviceError
        except asyncio.LimitOverrunError:
            self._log_error("Read buffer overrun.")
            self.close_connection()
            raise DeviceError
        self._queue.put_nowait(readwriter)

        ret = ret[:-9]
        error, returnedString = ret.split(b',', 1)
        error = int(error)
        if error != 0:
            self._log_error("Device returned error code: {0}".format(str(error)))
            raise DeviceError
        return (error, returnedString.decode())

    async def _query(self):
        """Periodically query group position and status."""
        try:
            while True:
                for i in range(self._group_num):
                    try:
                        group_name = self._group_names[i]
                        status = await self.GroupStatusGet(group_name)
                        self._group_status[i] = int(status[1])
                        position = await self.GroupPositionCurrentGet(group_name, 1)
                        self._group_positions[i] = float(position[1])
                    except ValueError:
                        # Would result in log spam
                        pass
                await asyncio.sleep(self._interval)
        except CancelledError:
            return

    async def initialize_all(self):
        if not self._connected:
            self._log_error("Not connected.")
            raise DeviceError
        await asyncio.gather(
            *[self.GroupInitialize(group_name) for group_name in self._group_names])

    async def home_all(self):
        if not self._connected:
            self.log_error("Not connected.")
            raise DeviceError
        await asyncio.gather(
            *[self.GroupHomeSearch(group_name) for group_name in self._group_names])

    async def kill_all(self):
        if not self._connected:
            self._log_error("Not connected.")
            raise DeviceError
        await asyncio.gather(
            *[self.GroupKill(group_name) for group_name in self._group_names])

    async def absolute_move(self, i, pos):
        group_name = self._group_names[i]
        if not self._backlash:
            await self.GroupMoveAbsolute(group_name, [str(pos)])
        else:
            current_pos = self._group_positions[i]
            if pos - current_pos < self._comp_amount:
                await self.GroupMoveAbsolute(group_name, [str(pos - self._comp_amount)])
                await self.GroupMoveAbsolute(group_name, [str(pos)])
            else:
                await self.GroupMoveAbsolute(group_name, [str(pos)])

    async def relative_move(self, i, pos):
        group_name = self._group_names[i]
        if not self._backlash:
            await self.GroupMoveRelative(group_name, [str(pos)])
        else:
            if pos < self._comp_amount:
                await self.GroupMoveRelative(group_name, [str(pos - self._comp_amount)])
                await self.GroupMoveRelative(group_name, [str(self._comp_amount)])
            else:
                await self.GroupMoveRelative(group_name, [str(pos)])

    async def open_connection(self, IP, port):
        if self._connected:
            self._log_warning("Already connected.")
            return
        try:
            for i in range(self._queue_size):
                readwriter = StreamReadWriter(*await wait_for(asyncio.open_connection(IP, port), timeout=self._timeout))
                self._readwriters.append(readwriter)
                self._queue.put_nowait(readwriter)
        except asyncio.TimeoutError:
            self._log_error("Connection timeout.")
            self.close_connection()
            raise DeviceError
        except Exception:
            self._log_exception("Failed to connect to {host}:{port}".format(host=IP, port=port))
            self.close_connection()
            raise DeviceError
        self._connected = True
        await self.init_device()

    async def init_device(self):
        """Initilize device after a successful `open_connection()`."""
        self._query_task = ensure_future(self._query())

    def close_connection(self):
        self._connected = False
        if self._query_task is not None:
            self._query_task.cancel()
            self._query_task = None
        for readwriter in self._readwriters:
            readwriter.close()
        self._readwriters.clear()
        self._queue = asyncio.Queue()

    # GetLibraryVersion
    async def GetLibraryVersion(self):
        return ['HXP Firmware V2.1.x']

    # ControllerMotionKernelTimeLoadGet :  Get controller motion kernel time
    # load
    async def ControllerMotionKernelTimeLoadGet(self):
        command = 'ControllerMotionKernelTimeLoadGet(double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(4):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # ElapsedTimeGet :  Return elapsed time from controller power on
    async def ElapsedTimeGet(self):
        command = 'ElapsedTimeGet(double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # ErrorStringGet :  Return the error string corresponding to the error code
    async def ErrorStringGet(self, ErrorCode):
        command = 'ErrorStringGet(' + str(ErrorCode) + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # FirmwareVersionGet :  Return firmware version
    async def FirmwareVersionGet(self):
        command = 'FirmwareVersionGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TCLScriptExecute :  Execute a TCL script from a TCL file
    async def TCLScriptExecute(self, TCLFileName, TaskName, ParametersList):
        command = 'TCLScriptExecute(' + TCLFileName + \
            ',' + TaskName + ',' + ParametersList + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TCLScriptExecuteAndWait :  Execute a TCL script from a TCL file and wait
    # the end of execution to return
    async def TCLScriptExecuteAndWait(self, TCLFileName, TaskName, InputParametersList):
        command = 'TCLScriptExecuteAndWait(' + TCLFileName + \
            ',' + TaskName + ',' + InputParametersList + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TCLScriptKill :  Kill TCL Task
    async def TCLScriptKill(self, TaskName):
        command = 'TCLScriptKill(' + TaskName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TCLScriptKillAll :  Kill all TCL Tasks
    async def TCLScriptKillAll(self):
        command = 'TCLScriptKillAll()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TimerGet :  Get a timer
    async def TimerGet(self, TimerName):
        command = 'TimerGet(' + TimerName + ',int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # TimerSet :  Set a timer
    async def TimerSet(self, TimerName, FrequencyTicks):
        command = 'TimerSet(' + TimerName + ',' + str(FrequencyTicks) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # Reboot :  Reboot the controller
    async def Reboot(self):
        command = 'Reboot()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # Login :  Log in
    async def Login(self, Name, Password):
        command = 'Login(' + Name + ',' + Password + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # CloseAllOtherSockets :  Close all socket beside the one used to send
    # this command
    async def CloseAllOtherSockets(self):
        command = 'CloseAllOtherSockets()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventAdd :  ** OBSOLETE ** Add an event
    async def EventAdd(self, PositionerName, EventName, EventParameter, ActionName, ActionParameter1, ActionParameter2, ActionParameter3):
        command = 'EventAdd(' + PositionerName + ',' + EventName + ',' + EventParameter + ',' + \
            ActionName + ',' + ActionParameter1 + ',' + \
            ActionParameter2 + ',' + ActionParameter3 + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventGet :  ** OBSOLETE ** Read events and actions list
    async def EventGet(self, PositionerName):
        command = 'EventGet(' + PositionerName + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventRemove :  ** OBSOLETE ** Delete an event
    async def EventRemove(self, PositionerName, EventName, EventParameter):
        command = 'EventRemove(' + PositionerName + ',' + \
            EventName + ',' + EventParameter + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventWait :  ** OBSOLETE ** Wait an event
    async def EventWait(self, PositionerName, EventName, EventParameter):
        command = 'EventWait(' + PositionerName + ',' + \
            EventName + ',' + EventParameter + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventExtendedConfigurationTriggerSet :  Configure one or several events
    async def EventExtendedConfigurationTriggerSet(self, ExtendedEventName, EventParameter1, EventParameter2, EventParameter3, EventParameter4):
        command = 'EventExtendedConfigurationTriggerSet('
        for i in range(len(ExtendedEventName)):
            if (i > 0):
                command += ','
            command += ExtendedEventName[i] + ',' + EventParameter1[i] + ',' + \
                EventParameter2[i] + ',' + \
                EventParameter3[i] + ',' + EventParameter4[i]
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventExtendedConfigurationTriggerGet :  Read the event configuration
    async def EventExtendedConfigurationTriggerGet(self):
        command = 'EventExtendedConfigurationTriggerGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventExtendedConfigurationActionSet :  Configure one or several actions
    async def EventExtendedConfigurationActionSet(self, ExtendedActionName, ActionParameter1, ActionParameter2, ActionParameter3, ActionParameter4):
        command = 'EventExtendedConfigurationActionSet('
        for i in range(len(ExtendedActionName)):
            if (i > 0):
                command += ','
            command += ExtendedActionName[i] + ',' + ActionParameter1[i] + ',' + \
                ActionParameter2[i] + ',' + \
                ActionParameter3[i] + ',' + ActionParameter4[i]
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventExtendedConfigurationActionGet :  Read the action configuration
    async def EventExtendedConfigurationActionGet(self):
        command = 'EventExtendedConfigurationActionGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventExtendedStart :  Launch the last event and action configuration and
    # return an ID
    async def EventExtendedStart(self):
        command = 'EventExtendedStart(int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # EventExtendedAllGet :  Read all event and action configurations
    async def EventExtendedAllGet(self):
        command = 'EventExtendedAllGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventExtendedGet :  Read the event and action configuration defined by ID
    async def EventExtendedGet(self, ID):
        command = 'EventExtendedGet(' + str(ID) + ',char *,char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventExtendedRemove :  Remove the event and action configuration defined
    # by ID
    async def EventExtendedRemove(self, ID):
        command = 'EventExtendedRemove(' + str(ID) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventExtendedWait :  Wait events from the last event configuration
    async def EventExtendedWait(self):
        command = 'EventExtendedWait()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringConfigurationGet :  Read different mnemonique type
    async def GatheringConfigurationGet(self):
        command = 'GatheringConfigurationGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringConfigurationSet :  Configuration acquisition
    async def GatheringConfigurationSet(self, Type):
        command = 'GatheringConfigurationSet('
        for i in range(len(Type)):
            if (i > 0):
                command += ','
            command += Type[i]
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringCurrentNumberGet :  Maximum number of samples and current
    # number during acquisition
    async def GatheringCurrentNumberGet(self):
        command = 'GatheringCurrentNumberGet(int *,int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # GatheringStopAndSave :  Stop acquisition and save data
    async def GatheringStopAndSave(self):
        command = 'GatheringStopAndSave()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringDataAcquire :  Acquire a configured data
    async def GatheringDataAcquire(self):
        command = 'GatheringDataAcquire()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringDataGet :  Get a data line from gathering buffer
    async def GatheringDataGet(self, IndexPoint):
        command = 'GatheringDataGet(' + str(IndexPoint) + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringReset :  Empty the gathered data in memory to start new
    # gathering from scratch
    async def GatheringReset(self):
        command = 'GatheringReset()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringRun :  Start a new gathering
    async def GatheringRun(self, DataNumber, Divisor):
        command = 'GatheringRun(' + str(DataNumber) + ',' + str(Divisor) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringStop :  Stop the data gathering (without saving to file)
    async def GatheringStop(self):
        command = 'GatheringStop()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringExternalConfigurationSet :  Configuration acquisition
    async def GatheringExternalConfigurationSet(self, Type):
        command = 'GatheringExternalConfigurationSet('
        for i in range(len(Type)):
            if (i > 0):
                command += ','
            command += Type[i]
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringExternalConfigurationGet :  Read different mnemonique type
    async def GatheringExternalConfigurationGet(self):
        command = 'GatheringExternalConfigurationGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringExternalCurrentNumberGet :  Maximum number of samples and
    # current number during acquisition
    async def GatheringExternalCurrentNumberGet(self):
        command = 'GatheringExternalCurrentNumberGet(int *,int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # GatheringExternalStopAndSave :  Stop acquisition and save data
    async def GatheringExternalStopAndSave(self):
        command = 'GatheringExternalStopAndSave()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GlobalArrayGet :  Get global array value
    async def GlobalArrayGet(self, Number):
        command = 'GlobalArrayGet(' + str(Number) + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GlobalArraySet :  Set global array value
    async def GlobalArraySet(self, Number, ValueString):
        command = 'GlobalArraySet(' + str(Number) + ',' + ValueString + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # DoubleGlobalArrayGet :  Get double global array value
    async def DoubleGlobalArrayGet(self, Number):
        command = 'DoubleGlobalArrayGet(' + str(Number) + ',double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # DoubleGlobalArraySet :  Set double global array value
    async def DoubleGlobalArraySet(self, Number, DoubleValue):
        command = 'DoubleGlobalArraySet(' + \
            str(Number) + ',' + str(DoubleValue) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GPIOAnalogGet :  Read analog input or analog output for one or few input
    async def GPIOAnalogGet(self, GPIOName):
        command = 'GPIOAnalogGet('
        for i in range(len(GPIOName)):
            if (i > 0):
                command += ','
            command += GPIOName[i] + ',' + 'double *'
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(len(GPIOName)):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # GPIOAnalogSet :  Set analog output for one or few output
    async def GPIOAnalogSet(self, GPIOName, AnalogOutputValue):
        command = 'GPIOAnalogSet('
        for i in range(len(GPIOName)):
            if (i > 0):
                command += ','
            command += GPIOName[i] + ',' + str(AnalogOutputValue[i])
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GPIOAnalogGainGet :  Read analog input gain (1, 2, 4 or 8) for one or
    # few input
    async def GPIOAnalogGainGet(self, GPIOName):
        command = 'GPIOAnalogGainGet('
        for i in range(len(GPIOName)):
            if (i > 0):
                command += ','
            command += GPIOName[i] + ',' + 'int *'
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(len(GPIOName)):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # GPIOAnalogGainSet :  Set analog input gain (1, 2, 4 or 8) for one or few
    # input
    async def GPIOAnalogGainSet(self, GPIOName, AnalogInputGainValue):
        command = 'GPIOAnalogGainSet('
        for i in range(len(GPIOName)):
            if (i > 0):
                command += ','
            command += GPIOName[i] + ',' + str(AnalogInputGainValue[i])
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GPIODigitalGet :  Read digital output or digital input
    async def GPIODigitalGet(self, GPIOName):
        command = 'GPIODigitalGet(' + GPIOName + ',unsigned short *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # GPIODigitalSet :  Set Digital Output for one or few output TTL
    async def GPIODigitalSet(self, GPIOName, Mask, DigitalOutputValue):
        command = 'GPIODigitalSet(' + GPIOName + ',' + \
            str(Mask) + ',' + str(DigitalOutputValue) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupCorrectorOutputGet :  Return corrector outputs
    async def GroupCorrectorOutputGet(self, GroupName, nbElement):
        command = 'GroupCorrectorOutputGet(' + GroupName + ','
        for i in range(nbElement):
            if (i > 0):
                command += ','
            command += 'double *'
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(nbElement):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # GroupHomeSearch :  Start home search sequence
    async def GroupHomeSearch(self, GroupName):
        command = 'GroupHomeSearch(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupHomeSearchAndRelativeMove :  Start home search sequence and execute
    # a displacement
    async def GroupHomeSearchAndRelativeMove(self, GroupName, TargetDisplacement):
        command = 'GroupHomeSearchAndRelativeMove(' + GroupName + ','
        for i in range(len(TargetDisplacement)):
            if (i > 0):
                command += ','
            command += str(TargetDisplacement[i])
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupReadyAtPosition :  Go to READY state with the users positions
    async def GroupReadyAtPosition(self, GroupName, EncoderPosition1, EncoderPosition2, EncoderPosition3, EncoderPosition4, EncoderPosition5, EncoderPosition6):
        command = 'GroupReadyAtPosition(' + GroupName + ',' + str(EncoderPosition1) + ',' + str(EncoderPosition2) + ',' + str(
            EncoderPosition3) + ',' + str(EncoderPosition4) + ',' + str(EncoderPosition5) + ',' + str(EncoderPosition6) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupInitialize :  Start the initialization
    async def GroupInitialize(self, GroupName):
        command = 'GroupInitialize(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupInitializeWithEncoderCalibration :  Start the initialization with
    # encoder calibration
    async def GroupInitializeWithEncoderCalibration(self, GroupName):
        command = 'GroupInitializeWithEncoderCalibration(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupKill :  Kill the group
    async def GroupKill(self, GroupName):
        command = 'GroupKill(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupMoveAbort :  Abort a move
    async def GroupMoveAbort(self, GroupName):
        command = 'GroupMoveAbort(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupMoveAbsolute :  Do an absolute move
    async def GroupMoveAbsolute(self, GroupName, TargetPosition):
        command = 'GroupMoveAbsolute(' + GroupName + ','
        for i in range(len(TargetPosition)):
            if (i > 0):
                command += ','
            command += str(TargetPosition[i])
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupMoveRelative :  Do a relative move
    async def GroupMoveRelative(self, GroupName, TargetDisplacement):
        command = 'GroupMoveRelative(' + GroupName + ','
        for i in range(len(TargetDisplacement)):
            if (i > 0):
                command += ','
            command += str(TargetDisplacement[i])
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupMotionDisable :  Set Motion disable on selected group
    async def GroupMotionDisable(self, GroupName):
        command = 'GroupMotionDisable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupMotionEnable :  Set Motion enable on selected group
    async def GroupMotionEnable(self, GroupName):
        command = 'GroupMotionEnable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupPositionCorrectedProfilerGet :  Return corrected profiler positions
    async def GroupPositionCorrectedProfilerGet(self, GroupName, PositionX, PositionY):
        command = 'GroupPositionCorrectedProfilerGet(' + GroupName + ',' + str(
            PositionX) + ',' + str(PositionY) + ',double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # GroupPositionCurrentGet :  Return current positions
    async def GroupPositionCurrentGet(self, GroupName, nbElement):
        command = 'GroupPositionCurrentGet(' + GroupName + ','
        for i in range(nbElement):
            if (i > 0):
                command += ','
            command += 'double *'
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(nbElement):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # GroupPositionSetpointGet :  Return setpoint positions
    async def GroupPositionSetpointGet(self, GroupName, nbElement):
        command = 'GroupPositionSetpointGet(' + GroupName + ','
        for i in range(nbElement):
            if (i > 0):
                command += ','
            command += 'double *'
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(nbElement):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # GroupPositionTargetGet :  Return target positions
    async def GroupPositionTargetGet(self, GroupName, nbElement):
        command = 'GroupPositionTargetGet(' + GroupName + ','
        for i in range(nbElement):
            if (i > 0):
                command += ','
            command += 'double *'
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(nbElement):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # GroupStatusGet :  Return group status
    async def GroupStatusGet(self, GroupName):
        command = 'GroupStatusGet(' + GroupName + ',int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # GroupStatusStringGet :  Return the group status string corresponding to
    # the group status code
    async def GroupStatusStringGet(self, GroupStatusCode):
        command = 'GroupStatusStringGet(' + str(GroupStatusCode) + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # KillAll :  Put all groups in 'Not initialized' state
    async def KillAll(self):
        command = 'KillAll()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # RestartApplication :  Restart the Controller
    async def RestartApplication(self):
        command = 'RestartApplication()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerBacklashGet :  Read backlash value and status
    async def PositionerBacklashGet(self, PositionerName):
        command = 'PositionerBacklashGet(' + \
            PositionerName + ',double *,char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerBacklashSet :  Set backlash value
    async def PositionerBacklashSet(self, PositionerName, BacklashValue):
        command = 'PositionerBacklashSet(' + PositionerName + \
            ',' + str(BacklashValue) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerBacklashEnable :  Enable the backlash
    async def PositionerBacklashEnable(self, PositionerName):
        command = 'PositionerBacklashEnable(' + PositionerName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerBacklashDisable :  Disable the backlash
    async def PositionerBacklashDisable(self, PositionerName):
        command = 'PositionerBacklashDisable(' + PositionerName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorNotchFiltersSet :  Update filters parameters
    async def PositionerCorrectorNotchFiltersSet(self, PositionerName, NotchFrequency1, NotchBandwith1, NotchGain1, NotchFrequency2, NotchBandwith2, NotchGain2):
        command = 'PositionerCorrectorNotchFiltersSet(' + PositionerName + ',' + str(NotchFrequency1) + ',' + str(
            NotchBandwith1) + ',' + str(NotchGain1) + ',' + str(NotchFrequency2) + ',' + str(NotchBandwith2) + ',' + str(NotchGain2) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorNotchFiltersGet :  Read filters parameters
    async def PositionerCorrectorNotchFiltersGet(self, PositionerName):
        command = 'PositionerCorrectorNotchFiltersGet(' + PositionerName + \
            ',double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(6):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerCorrectorPIDFFAccelerationSet :  Update corrector parameters
    async def PositionerCorrectorPIDFFAccelerationSet(self, PositionerName, ClosedLoopStatus, KP, KI, KD, KS, IntegrationTime, DerivativeFilterCutOffFrequency, GKP, GKI, GKD, KForm, FeedForwardGainAcceleration):
        command = 'PositionerCorrectorPIDFFAccelerationSet(' + PositionerName + ',' + str(ClosedLoopStatus) + ',' + str(KP) + ',' + str(KI) + ',' + str(KD) + ',' + str(KS) + ',' + str(
            IntegrationTime) + ',' + str(DerivativeFilterCutOffFrequency) + ',' + str(GKP) + ',' + str(GKI) + ',' + str(GKD) + ',' + str(KForm) + ',' + str(FeedForwardGainAcceleration) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorPIDFFAccelerationGet :  Read corrector parameters
    async def PositionerCorrectorPIDFFAccelerationGet(self, PositionerName):
        command = 'PositionerCorrectorPIDFFAccelerationGet(' + PositionerName + \
            ',bool *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(12):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerCorrectorPIDFFVelocitySet :  Update corrector parameters
    async def PositionerCorrectorPIDFFVelocitySet(self, PositionerName, ClosedLoopStatus, KP, KI, KD, KS, IntegrationTime, DerivativeFilterCutOffFrequency, GKP, GKI, GKD, KForm, FeedForwardGainVelocity):
        command = 'PositionerCorrectorPIDFFVelocitySet(' + PositionerName + ',' + str(ClosedLoopStatus) + ',' + str(KP) + ',' + str(KI) + ',' + str(KD) + ',' + str(KS) + ',' + str(
            IntegrationTime) + ',' + str(DerivativeFilterCutOffFrequency) + ',' + str(GKP) + ',' + str(GKI) + ',' + str(GKD) + ',' + str(KForm) + ',' + str(FeedForwardGainVelocity) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorPIDFFVelocityGet :  Read corrector parameters
    async def PositionerCorrectorPIDFFVelocityGet(self, PositionerName):
        command = 'PositionerCorrectorPIDFFVelocityGet(' + PositionerName + \
            ',bool *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(12):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerCorrectorPIDDualFFVoltageSet :  Update corrector parameters
    async def PositionerCorrectorPIDDualFFVoltageSet(self, PositionerName, ClosedLoopStatus, KP, KI, KD, KS, IntegrationTime, DerivativeFilterCutOffFrequency, GKP, GKI, GKD, KForm, FeedForwardGainVelocity, FeedForwardGainAcceleration, Friction):
        command = 'PositionerCorrectorPIDDualFFVoltageSet(' + PositionerName + ',' + str(ClosedLoopStatus) + ',' + str(KP) + ',' + str(KI) + ',' + str(KD) + ',' + str(KS) + ',' + str(IntegrationTime) + ',' + str(
            DerivativeFilterCutOffFrequency) + ',' + str(GKP) + ',' + str(GKI) + ',' + str(GKD) + ',' + str(KForm) + ',' + str(FeedForwardGainVelocity) + ',' + str(FeedForwardGainAcceleration) + ',' + str(Friction) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorPIDDualFFVoltageGet :  Read corrector parameters
    async def PositionerCorrectorPIDDualFFVoltageGet(self, PositionerName):
        command = 'PositionerCorrectorPIDDualFFVoltageGet(' + PositionerName + \
            ',bool *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(14):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerCorrectorPIPositionSet :  Update corrector parameters
    async def PositionerCorrectorPIPositionSet(self, PositionerName, ClosedLoopStatus, KP, KI, IntegrationTime):
        command = 'PositionerCorrectorPIPositionSet(' + PositionerName + ',' + str(
            ClosedLoopStatus) + ',' + str(KP) + ',' + str(KI) + ',' + str(IntegrationTime) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorPIPositionGet :  Read corrector parameters
    async def PositionerCorrectorPIPositionGet(self, PositionerName):
        command = 'PositionerCorrectorPIPositionGet(' + \
            PositionerName + ',bool *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(4):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerCorrectorTypeGet :  Read corrector type
    async def PositionerCorrectorTypeGet(self, PositionerName):
        command = 'PositionerCorrectorTypeGet(' + PositionerName + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCurrentVelocityAccelerationFiltersSet :  Set current velocity
    # and acceleration cut off frequencies
    async def PositionerCurrentVelocityAccelerationFiltersSet(self, PositionerName, CurrentVelocityCutOffFrequency, CurrentAccelerationCutOffFrequency):
        command = 'PositionerCurrentVelocityAccelerationFiltersSet(' + PositionerName + ',' + str(
            CurrentVelocityCutOffFrequency) + ',' + str(CurrentAccelerationCutOffFrequency) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCurrentVelocityAccelerationFiltersGet :  Get current velocity
    # and acceleration cut off frequencies
    async def PositionerCurrentVelocityAccelerationFiltersGet(self, PositionerName):
        command = 'PositionerCurrentVelocityAccelerationFiltersGet(' + \
            PositionerName + ',double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerDriverStatusGet :  Read positioner driver status
    async def PositionerDriverStatusGet(self, PositionerName):
        command = 'PositionerDriverStatusGet(' + PositionerName + ',int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # PositionerDriverStatusStringGet :  Return the positioner driver status
    # string corresponding to the positioner error code
    async def PositionerDriverStatusStringGet(self, PositionerDriverStatus):
        command = 'PositionerDriverStatusStringGet(' + str(
            PositionerDriverStatus) + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerEncoderAmplitudeValuesGet :  Read analog interpolated encoder
    # amplitude values
    async def PositionerEncoderAmplitudeValuesGet(self, PositionerName):
        command = 'PositionerEncoderAmplitudeValuesGet(' + \
            PositionerName + ',double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(4):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerEncoderCalibrationParametersGet :  Read analog interpolated
    # encoder calibration parameters
    async def PositionerEncoderCalibrationParametersGet(self, PositionerName):
        command = 'PositionerEncoderCalibrationParametersGet(' + \
            PositionerName + ',double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(4):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerErrorGet :  Read and clear positioner error code
    async def PositionerErrorGet(self, PositionerName):
        command = 'PositionerErrorGet(' + PositionerName + ',int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # PositionerErrorRead :  Read only positioner error code without clear it
    async def PositionerErrorRead(self, PositionerName):
        command = 'PositionerErrorRead(' + PositionerName + ',int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # PositionerErrorStringGet :  Return the positioner status string
    # corresponding to the positioner error code
    async def PositionerErrorStringGet(self, PositionerErrorCode):
        command = 'PositionerErrorStringGet(' + \
            str(PositionerErrorCode) + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerHardwareStatusGet :  Read positioner hardware status
    async def PositionerHardwareStatusGet(self, PositionerName):
        command = 'PositionerHardwareStatusGet(' + PositionerName + ',int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # PositionerHardwareStatusStringGet :  Return the positioner hardware
    # status string corresponding to the positioner error code
    async def PositionerHardwareStatusStringGet(self, PositionerHardwareStatus):
        command = 'PositionerHardwareStatusStringGet(' + str(
            PositionerHardwareStatus) + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerHardInterpolatorFactorGet :  Get hard interpolator parameters
    async def PositionerHardInterpolatorFactorGet(self, PositionerName):
        command = 'PositionerHardInterpolatorFactorGet(' + \
            PositionerName + ',int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # PositionerHardInterpolatorFactorSet :  Set hard interpolator parameters
    async def PositionerHardInterpolatorFactorSet(self, PositionerName, InterpolationFactor):
        command = 'PositionerHardInterpolatorFactorSet(' + PositionerName + ',' + str(
            InterpolationFactor) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerMaximumVelocityAndAccelerationGet :  Return maximum velocity
    # and acceleration of the positioner
    async def PositionerMaximumVelocityAndAccelerationGet(self, PositionerName):
        command = 'PositionerMaximumVelocityAndAccelerationGet(' + \
            PositionerName + ',double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerMotionDoneGet :  Read motion done parameters
    async def PositionerMotionDoneGet(self, PositionerName):
        command = 'PositionerMotionDoneGet(' + PositionerName + \
            ',double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(5):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerMotionDoneSet :  Update motion done parameters
    async def PositionerMotionDoneSet(self, PositionerName, PositionWindow, VelocityWindow, CheckingTime, MeanPeriod, TimeOut):
        command = 'PositionerMotionDoneSet(' + PositionerName + ',' + str(PositionWindow) + ',' + str(
            VelocityWindow) + ',' + str(CheckingTime) + ',' + str(MeanPeriod) + ',' + str(TimeOut) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerSGammaExactVelocityAjustedDisplacementGet :  Return adjusted
    # displacement to get exact velocity
    async def PositionerSGammaExactVelocityAjustedDisplacementGet(self, PositionerName, DesiredDisplacement):
        command = 'PositionerSGammaExactVelocityAjustedDisplacementGet(' + PositionerName + ',' + str(
            DesiredDisplacement) + ',double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # PositionerSGammaParametersGet :  Read dynamic parameters for one axe of
    # a group for a future displacement
    async def PositionerSGammaParametersGet(self, PositionerName):
        command = 'PositionerSGammaParametersGet(' + PositionerName + \
            ',double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(4):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerSGammaParametersSet :  Update dynamic parameters for one axe
    # of a group for a future displacement
    async def PositionerSGammaParametersSet(self, PositionerName, Velocity, Acceleration, MinimumTjerkTime, MaximumTjerkTime):
        command = 'PositionerSGammaParametersSet(' + PositionerName + ',' + str(Velocity) + ',' + str(
            Acceleration) + ',' + str(MinimumTjerkTime) + ',' + str(MaximumTjerkTime) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerSGammaParametersDistanceGet :  Returns distance during
    # acceleration phase and distance during constant velocity phase
    async def PositionerSGammaParametersDistanceGet(self, PositionerName, Displacement, Velocity, Acceleration, MinJerkTime, MaxJerkTime):
        command = 'PositionerSGammaParametersDistanceGet(' + PositionerName + ',' + str(Displacement) + ',' + str(
            Velocity) + ',' + str(Acceleration) + ',' + str(MinJerkTime) + ',' + str(MaxJerkTime) + ',double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerSGammaPreviousMotionTimesGet :  Read SettingTime and
    # SettlingTime
    async def PositionerSGammaPreviousMotionTimesGet(self, PositionerName):
        command = 'PositionerSGammaPreviousMotionTimesGet(' + \
            PositionerName + ',double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerStageParameterGet :  Return the stage parameter
    async def PositionerStageParameterGet(self, PositionerName, ParameterName):
        command = 'PositionerStageParameterGet(' + \
            PositionerName + ',' + ParameterName + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerStageParameterSet :  Save the stage parameter
    async def PositionerStageParameterSet(self, PositionerName, ParameterName, ParameterValue):
        command = 'PositionerStageParameterSet(' + PositionerName + \
            ',' + ParameterName + ',' + ParameterValue + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerUserTravelLimitsGet :  Read UserMinimumTarget and
    # UserMaximumTarget
    async def PositionerUserTravelLimitsGet(self, PositionerName):
        command = 'PositionerUserTravelLimitsGet(' + \
            PositionerName + ',double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerUserTravelLimitsSet :  Update UserMinimumTarget and
    # UserMaximumTarget
    async def PositionerUserTravelLimitsSet(self, PositionerName, UserMinimumTarget, UserMaximumTarget):
        command = 'PositionerUserTravelLimitsSet(' + PositionerName + ',' + str(
            UserMinimumTarget) + ',' + str(UserMaximumTarget) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # HexapodMoveAbsolute :  Hexapod absolute move in a specific coordinate
    # system
    async def HexapodMoveAbsolute(self, GroupName, CoordinateSystem, X, Y, Z, U, V, W):
        command = 'HexapodMoveAbsolute(' + GroupName + ',' + CoordinateSystem + ',' + str(
            X) + ',' + str(Y) + ',' + str(Z) + ',' + str(U) + ',' + str(V) + ',' + str(W) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # HexapodMoveIncremental :  Hexapod incremental move in a specific
    # coordinate system
    async def HexapodMoveIncremental(self, GroupName, CoordinateSystem, dX, dY, dZ, dU, dV, dW):
        command = 'HexapodMoveIncremental(' + GroupName + ',' + CoordinateSystem + ',' + str(
            dX) + ',' + str(dY) + ',' + str(dZ) + ',' + str(dU) + ',' + str(dV) + ',' + str(dW) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # HexapodCoordinatesGet :  Get coordinates in a specific coordinate system
    # of a point specified in another coordinate system
    async def HexapodCoordinatesGet(self, GroupName, CoordinateSystemIn, CoordinateSystemOut, Xin, Yin, Zin, Uin, Vin, Win):
        command = 'HexapodCoordinatesGet(' + GroupName + ',' + CoordinateSystemIn + ',' + CoordinateSystemOut + ',' + str(Xin) + ',' + str(
            Yin) + ',' + str(Zin) + ',' + str(Uin) + ',' + str(Vin) + ',' + str(Win) + ',double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(6):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # HexapodCoordinateSystemSet :  Modify the position of a coordinate system
    async def HexapodCoordinateSystemSet(self, GroupName, CoordinateSystem, X, Y, Z, U, V, W):
        command = 'HexapodCoordinateSystemSet(' + GroupName + ',' + CoordinateSystem + ',' + str(
            X) + ',' + str(Y) + ',' + str(Z) + ',' + str(U) + ',' + str(V) + ',' + str(W) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # HexapodCoordinateSystemGet :  Get the position of a coordinate system
    async def HexapodCoordinateSystemGet(self, GroupName, CoordinateSystem):
        command = 'HexapodCoordinateSystemGet(' + GroupName + ',' + CoordinateSystem + \
            ',double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(6):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # HexapodMoveIncrementalControl :  Hexapod trajectory (Line, Arc or
    # Rotation) execution with the maximum velocity
    async def HexapodMoveIncrementalControl(self, GroupName, CoordinateSystem, HexapodTrajectoryType, dX, dY, dZ):
        command = 'HexapodMoveIncrementalControl(' + GroupName + ',' + CoordinateSystem + \
            ',' + HexapodTrajectoryType + ',' + \
            str(dX) + ',' + str(dY) + ',' + str(dZ) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # HexapodMoveIncrementalControlWithTargetVelocity :  Hexapod trajectory
    # (Line, Arc or Rotation) execution with a target velocity
    async def HexapodMoveIncrementalControlWithTargetVelocity(self, GroupName, CoordinateSystem, HexapodTrajectoryType, dX, dY, dZ, Velocity):
        command = 'HexapodMoveIncrementalControlWithTargetVelocity(' + GroupName + ',' + CoordinateSystem + ',' + HexapodTrajectoryType + ',' + str(
            dX) + ',' + str(dY) + ',' + str(dZ) + ',' + str(Velocity) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # HexapodMoveIncrementalControlPulseAndGatheringSet :  Configure gathering
    # with pulses : gathered data are X, Y, Z, U, V, W and pulses will be
    # generated during only constant velocity
    async def HexapodMoveIncrementalControlPulseAndGatheringSet(self, GroupName, Divisor):
        command = 'HexapodMoveIncrementalControlPulseAndGatheringSet(' + GroupName + ',' + str(
            Divisor) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # HexapodMoveIncrementalControlLimitGet :  Returns the maximum velocity of
    # carriage and the percent of the trajectory executable
    async def HexapodMoveIncrementalControlLimitGet(self, GroupName, CoordinateSystem, HexapodTrajectoryType, dX, dY, dZ):
        command = 'HexapodMoveIncrementalControlLimitGet(' + GroupName + ',' + CoordinateSystem + ',' + \
            HexapodTrajectoryType + ',' + \
            str(dX) + ',' + str(dY) + ',' + str(dZ) + ',double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # HexapodSGammaParametersDistanceGet :  Returns distance during
    # acceleration phase and distance during constant velocity phase for a
    # virtual SGamma profiler
    async def HexapodSGammaParametersDistanceGet(self, PositionerName, Displacement, Velocity, Acceleration, MinJerkTime, MaxJerkTime):
        command = 'HexapodSGammaParametersDistanceGet(' + PositionerName + ',' + str(Displacement) + ',' + str(
            Velocity) + ',' + str(Acceleration) + ',' + str(MinJerkTime) + ',' + str(MaxJerkTime) + ',double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # OptionalModuleExecute :  Execute an optional module
    async def OptionalModuleExecute(self, ModuleFileName, TaskName):
        command = 'OptionalModuleExecute(' + \
            ModuleFileName + ',' + TaskName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # OptionalModuleKill :  Kill an optional module
    async def OptionalModuleKill(self, TaskName):
        command = 'OptionalModuleKill(' + TaskName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # ControllerStatusGet :  Read controller current status
    async def ControllerStatusGet(self):
        command = 'ControllerStatusGet(int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # ControllerStatusStringGet :  Return the controller status string
    # corresponding to the controller status code
    async def ControllerStatusStringGet(self, ControllerStatusCode):
        command = 'ControllerStatusStringGet(' + \
            str(ControllerStatusCode) + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EEPROMCIESet :  Set CIE EEPROM reference string
    async def EEPROMCIESet(self, CardNumber, ReferenceString):
        command = 'EEPROMCIESet(' + str(CardNumber) + \
            ',' + ReferenceString + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EEPROMDACOffsetCIESet :  Set CIE DAC offsets
    async def EEPROMDACOffsetCIESet(self, PlugNumber, DAC1Offset, DAC2Offset):
        command = 'EEPROMDACOffsetCIESet(' + str(PlugNumber) + \
            ',' + str(DAC1Offset) + ',' + str(DAC2Offset) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EEPROMDriverSet :  Set Driver EEPROM reference string
    async def EEPROMDriverSet(self, PlugNumber, ReferenceString):
        command = 'EEPROMDriverSet(' + str(PlugNumber) + \
            ',' + ReferenceString + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EEPROMINTSet :  Set INT EEPROM reference string
    async def EEPROMINTSet(self, CardNumber, ReferenceString):
        command = 'EEPROMINTSet(' + str(CardNumber) + \
            ',' + ReferenceString + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # CPUCoreAndBoardSupplyVoltagesGet :  Get power informations
    async def CPUCoreAndBoardSupplyVoltagesGet(self):
        command = 'CPUCoreAndBoardSupplyVoltagesGet(double *,double *,double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(8):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # CPUTemperatureAndFanSpeedGet :  Get CPU temperature and fan speed
    async def CPUTemperatureAndFanSpeedGet(self):
        command = 'CPUTemperatureAndFanSpeedGet(double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # ActionListGet :  Action list
    async def ActionListGet(self):
        command = 'ActionListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # ActionExtendedListGet :  Action extended list
    async def ActionExtendedListGet(self):
        command = 'ActionExtendedListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # APIExtendedListGet :  API method list
    async def APIExtendedListGet(self):
        command = 'APIExtendedListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # APIListGet :  API method list without extended API
    async def APIListGet(self):
        command = 'APIListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # ErrorListGet :  Error list
    async def ErrorListGet(self):
        command = 'ErrorListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EventListGet :  General event list
    async def EventListGet(self):
        command = 'EventListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringListGet :  Gathering type list
    async def GatheringListGet(self):
        command = 'GatheringListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringExtendedListGet :  Gathering type extended list
    async def GatheringExtendedListGet(self):
        command = 'GatheringExtendedListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringExternalListGet :  External Gathering type list
    async def GatheringExternalListGet(self):
        command = 'GatheringExternalListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupStatusListGet :  Group status list
    async def GroupStatusListGet(self):
        command = 'GroupStatusListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # HardwareInternalListGet :  Internal hardware list
    async def HardwareInternalListGet(self):
        command = 'HardwareInternalListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # HardwareDriverAndStageGet :  Smart hardware
    async def HardwareDriverAndStageGet(self, PlugNumber):
        command = 'HardwareDriverAndStageGet(' + \
            str(PlugNumber) + ',char *,char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # HexapodTrajectoryListGet :  Hexapod trajectory type list
    async def HexapodTrajectoryListGet(self):
        command = 'HexapodTrajectoryListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # ObjectsListGet :  Group name and positioner name
    async def ObjectsListGet(self):
        command = 'ObjectsListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerErrorListGet :  Positioner error list
    async def PositionerErrorListGet(self):
        command = 'PositionerErrorListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerHardwareStatusListGet :  Positioner hardware status list
    async def PositionerHardwareStatusListGet(self):
        command = 'PositionerHardwareStatusListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerDriverStatusListGet :  Positioner driver status list
    async def PositionerDriverStatusListGet(self):
        command = 'PositionerDriverStatusListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # ReferencingActionListGet :  Get referencing action list
    async def ReferencingActionListGet(self):
        command = 'ReferencingActionListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # ReferencingSensorListGet :  Get referencing sensor list
    async def ReferencingSensorListGet(self):
        command = 'ReferencingSensorListGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GatheringUserDatasGet :  Return UserDatas values
    async def GatheringUserDatasGet(self):
        command = 'GatheringUserDatasGet(double *,double *,double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(8):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # ControllerMotionKernelPeriodMinMaxGet :  Get controller motion kernel
    # min/max periods
    async def ControllerMotionKernelPeriodMinMaxGet(self):
        command = 'ControllerMotionKernelPeriodMinMaxGet(double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(6):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # ControllerMotionKernelPeriodMinMaxReset :  Reset controller motion
    # kernel min/max periods
    async def ControllerMotionKernelPeriodMinMaxReset(self):
        command = 'ControllerMotionKernelPeriodMinMaxReset()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TestTCP :  Test TCP/IP transfert
    async def TestTCP(self, InputString):
        command = 'TestTCP(' + InputString + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PrepareForUpdate :  Kill QNX processes for firmware update
    async def PrepareForUpdate(self):
        command = 'PrepareForUpdate()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)
