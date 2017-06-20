"""Smartlink device for Newport Motion Controller."""
# XPS Python class
#
# for XPS-Q8 Firmware Precision Platform V1.4.x
#
# See Programmer's manual for more information on XPS function calls
#
# Modified to use asyncio

import asyncio
from asyncio import wait_for, ensure_future
from concurrent.futures import CancelledError

from smartlink import node


class XPS(node.Device):
    """Smartlink device for XPS-Q8 Motion Controller."""
    # Initialization Function

    def __init__(self, name="XPS-Q8", group_names=[], interval=0.1,
            loop=None, queue_size=10):
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
        self._group_names = group_names
        self._group_num = len(self._group_names)
        self._group_status = ['0'] * self._group_num
        self._group_compensation = ['0'] * self._group_num
        self._group_positions = [0] * self._group_num

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

        for i in range(self._group_num):
            group_name = self._group_names[i]
            self.add_update("Positon", "float",
                lambda i=i: self._group_positions[i], grp=group_name)
            self.add_update("Status", "Int",
                lambda i=i: self._group_status[i], grp=group_name)
            self.add_command("Absolute move", "float",
                lambda pos, i=i: ensure_future(self.absolute_move(i, pos)), grp=group_name)
            self.add_command("Relative move", "float",
                lambda pos, i=i: ensure_future(self.relative_move(i, pos)), grp=group_name)
            self.add_command("Relative move", "float",
                lambda pos, i=i: ensure_future(self.relative_move(i, pos)), grp=group_name)

    def set_backlash(self, backlash):
        """Enable/disable backlash compensation."""
        if backlash == '0':
            self._backlash = False
        elif backlash == '1':
            self._backlash = True
        else:
            self.logger.error(
                self.fullname, "Unrecognized boolean value: {0}".format(backlash))

    def set_comp_amount(self, amount):
        try:
            self._comp_amount = float(amount)
        except ValueError:
            self.logger.error(
                self.fullname, "Invalid backlash compensation amount: {0}".format(amount))

    async def _query(self):
        """Periodically query group position and status."""
        try:
            while True:
                for i in range(self._group_num):
                    group_name = self._group_names[i]
                    status = await self.GroupStatusGet(group_name)
                    self._group_status[i] = status[1]
                    position = await self.GroupPositionCurrentGet(group_name, 1)
                    self._group_positions[i] = float(position[1])
                await asyncio.sleep(self._interval)
        except CancelledError:
            return

    async def initialize_all(self):
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return
        await asyncio.gather(
            *[self.GroupInitialize(group_name) for group_name in self._group_names])
        # await self.get_status_all()

    async def home_all(self):
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return
        await asyncio.gather(
            *[self.GroupHomeSearch(group_name) for group_name in self._group_names])
        # await self.get_status_all()
        # await self.get_positions_all()

    async def kill_all(self):
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return
        await asyncio.gather(
            *[self.GroupKill(group_name) for group_name in self._group_names])
        # await self.get_status_all()

    async def get_status_all(self):
        """Get group status for all groups."""
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return
        status = await asyncio.gather(
            *[self.GroupStatusGet(group_name) for group_name in self._group_names])
        for i in range(self._group_num):
            self._group_status[i] = status[i][1]

    async def get_positions_all(self):
        """Get the position for all groups."""
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return
        positions = await asyncio.gather(
            *[self.GroupPositionCurrentGet(group_name, 1) for group_name in self._group_names])
        for i in range(self._group_num):
            self._group_positions[i] = float(positions[i][1])

    async def absolute_move(self, i, pos):
        group_name = self._group_names[i]
        if not self._backlash:
            await self.GroupMoveAbsolute(group_name, [pos])
        else:
            target_pos = float(pos)
            current_pos = self._group_positions[i]
            if target_pos - current_pos < self._comp_amount:
                await self.GroupMoveAbsolute(group_name, [str(target_pos - self._comp_amount)])
                await self.GroupMoveAbsolute(group_name, [pos])
            else:
                await self.GroupMoveAbsolute(group_name, [pos])

        # status = await self.GroupStatusGet(group_name)
        # self._group_status[i] = status[1]
        # position = await self.GroupPositionCurrentGet(group_name, 1)
        # self._group_positions[i] = float(position[1])

    async def relative_move(self, i, pos):
        group_name = self._group_names[i]
        if not self._backlash:
            await self.GroupMoveRelative(group_name, [pos])
        else:
            target_pos = float(pos)
            if target_pos < self._comp_amount:
                await self.GroupMoveRelative(group_name, [str(target_pos - self._comp_amount)])
                await self.GroupMoveRelative(group_name, [str(self._comp_amount)])
            else:
                await self.GroupMoveRelative(group_name, [pos])

        # status = await self.GroupStatusGet(group_name)
        # self._group_status[i] = status[1]
        # position = await self.GroupPositionCurrentGet(group_name, 1)
        # self._group_positions[i] = float(position[1])

    async def _sendAndReceive(self, command):
        """Send command and get return."""
        if not self._connected:
            self.logger.error(self.fullname, "Not connected.")
            return (-2, '')

        readwriter = await self._queue.get()
        reader = readwriter[0]
        writer = readwriter[1]
        try:
            writer.write(command.encode("ascii"))
            ret = await wait_for(reader.readuntil(b",EndOfAPI"), timeout=self._timeout)
        except asyncio.TimeoutError:
            self.logger.error(self.fullname, "Read timeout.")
            self.close_connection()
            return (-2, '')
        except asyncio.IncompleteReadError:
            self.logger.error(self.fullname, "Connection lost while reading.")
            self.close_connection()
            return (-2, '')
        except asyncio.LimitOverrunError:
            self.logger.error(self.fullname, "Read buffer overrun.")
            self.close_connection()
            return (-2, '')
        self._queue.put_nowait(readwriter)

        ret = ret[:-9]
        error, returnedString = ret.split(b',', 1)
        return (int(error), returnedString.decode("ascii"))

    async def DisplayErrorAndClose(self, errorCode, APIName):
        if (errorCode != -2) and (errorCode != -108):
            (errorCode2, errorString) = await self.ErrorStringGet(errorCode)
            if (errorCode2 != 0):
                self.logger.error(self.fullname, ' '.join(
                    (APIName, ': ERROR ', str(errorCode))))
            else:
                self.logger.error(self.fullname, ' '.join(
                    (APIName, ': ', errorString)))
        else:
            if (errorCode == -2):
                pass    # Already logged
            if (errorCode == -108):
                self.logger.error(self.fullname, ' '.join(
                    (APIName, ': The TCP/IP connection was closed by an administrator')))
        self.close_connection()

    async def open_connection(self, IP, port):
        if self._connected:
            # self.logger.error(self.fullname, "Already connected.")
            return
        try:
            for i in range(self._queue_size):
                readwriter = await asyncio.open_connection(IP, port)
                self._readwriters.append(readwriter)
                self._queue.put_nowait(readwriter)
            self._connected = True
        except Exception:
            self.logger.exception(
                self.fullname, "Failed to connect to {host}:{port}".format(
                    host=IP, port=port))
            self.close_connection()
            return

        self._query_task = ensure_future(self._query())

    def close_connection(self):
        self._connected = False
        if self._query_task is not None:
            self._query_task.cancel()
            self._query_task = None
        for readwriter in self._readwriters:
            readwriter[1].close()
        self._readwriters.clear()
        self._queue = asyncio.Queue()

    # GetLibraryVersion
    def GetLibraryVersion(self):
        return ['XPS-Q8 Firmware Precision Platform V1.4.x']

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

    # ControllerRTTimeGet :  Get controller corrector period and calculation
    # time
    async def ControllerRTTimeGet(self):
        command = 'ControllerRTTimeGet(double *,double *)'
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

    # ControllerSlaveStatusGet :  Read slave controller status
    async def ControllerSlaveStatusGet(self):
        command = 'ControllerSlaveStatusGet(int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # ControllerSlaveStatusStringGet :  Return the slave controller status
    # string
    async def ControllerSlaveStatusStringGet(self, SlaveControllerStatusCode):
        command = 'ControllerSlaveStatusStringGet(' + str(
            SlaveControllerStatusCode) + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # ControllerSynchronizeCorrectorISR :  Synchronize controller corrector ISR
    async def ControllerSynchronizeCorrectorISR(self, ModeString):
        command = 'ControllerSynchronizeCorrectorISR(' + ModeString + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # ControllerStatusGet :  Get controller current status and reset the status
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

    # ControllerStatusRead :  Read controller current status
    async def ControllerStatusRead(self):
        command = 'ControllerStatusRead(int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # ControllerStatusStringGet :  Return the controller status string
    async def ControllerStatusStringGet(self, ControllerStatusCode):
        command = 'ControllerStatusStringGet(' + \
            str(ControllerStatusCode) + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

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

    # InstallerVersionGet :  Return installer version
    async def InstallerVersionGet(self):
        command = 'InstallerVersionGet(char *)'
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

    # TCLScriptExecuteWithPriority :  Execute a TCL script with defined
    # priority
    async def TCLScriptExecuteWithPriority(self, TCLFileName, TaskName, TaskPriorityLevel, ParametersList):
        command = 'TCLScriptExecuteWithPriority(' + TCLFileName + ',' + \
            TaskName + ',' + TaskPriorityLevel + ',' + ParametersList + ')'
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

    # HardwareDateAndTimeGet :  Return hardware date and time
    async def HardwareDateAndTimeGet(self):
        command = 'HardwareDateAndTimeGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # HardwareDateAndTimeSet :  Set hardware date and time
    async def HardwareDateAndTimeSet(self, DateAndTime):
        command = 'HardwareDateAndTimeSet(' + DateAndTime + ')'
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

    # GatheringConfigurationGet : Read different mnemonique type
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

    # GatheringDataMultipleLinesGet :  Get multiple data lines from gathering
    # buffer
    async def GatheringDataMultipleLinesGet(self, IndexPoint, NumberOfLines):
        command = 'GatheringDataMultipleLinesGet(' + str(
            IndexPoint) + ',' + str(NumberOfLines) + ',char *)'
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

    # GatheringRunAppend :  Re-start the stopped gathering to add new data
    async def GatheringRunAppend(self):
        command = 'GatheringRunAppend()'
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

    # GatheringExternalDataGet :  Get a data line from external gathering
    # buffer
    async def GatheringExternalDataGet(self, IndexPoint):
        command = 'GatheringExternalDataGet(' + str(IndexPoint) + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

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

    # GroupAccelerationSetpointGet :  Return setpoint accelerations
    async def GroupAccelerationSetpointGet(self, GroupName, nbElement):
        command = 'GroupAccelerationSetpointGet(' + GroupName + ','
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

    # GroupAnalogTrackingModeEnable :  Enable Analog Tracking mode on selected
    # group
    async def GroupAnalogTrackingModeEnable(self, GroupName, Type):
        command = 'GroupAnalogTrackingModeEnable(' + \
            GroupName + ',' + Type + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupAnalogTrackingModeDisable :  Disable Analog Tracking mode on
    # selected group
    async def GroupAnalogTrackingModeDisable(self, GroupName):
        command = 'GroupAnalogTrackingModeDisable(' + GroupName + ')'
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

    # GroupCurrentFollowingErrorGet :  Return current following errors
    async def GroupCurrentFollowingErrorGet(self, GroupName, nbElement):
        command = 'GroupCurrentFollowingErrorGet(' + GroupName + ','
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

    # GroupInitialize :  Start the initialization
    async def GroupInitialize(self, GroupName):
        command = 'GroupInitialize(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupInitializeNoEncoderReset :  Group initialization with no encoder
    # reset
    async def GroupInitializeNoEncoderReset(self, GroupName):
        command = 'GroupInitializeNoEncoderReset(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupInitializeWithEncoderCalibration :  Group initialization with
    # encoder calibration
    async def GroupInitializeWithEncoderCalibration(self, GroupName):
        command = 'GroupInitializeWithEncoderCalibration(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupInterlockDisable :  Set group interlock disable
    async def GroupInterlockDisable(self, GroupName):
        command = 'GroupInterlockDisable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupInterlockEnable :  Set group interlock enable
    async def GroupInterlockEnable(self, GroupName):
        command = 'GroupInterlockEnable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupJogParametersSet :  Modify Jog parameters on selected group and
    # activate the continuous move
    async def GroupJogParametersSet(self, GroupName, Velocity, Acceleration):
        command = 'GroupJogParametersSet(' + GroupName + ','
        for i in range(len(Velocity)):
            if (i > 0):
                command += ','
            command += str(Velocity[i]) + ',' + str(Acceleration[i])
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupJogParametersGet :  Get Jog parameters on selected group
    async def GroupJogParametersGet(self, GroupName, nbElement):
        command = 'GroupJogParametersGet(' + GroupName + ','
        for i in range(nbElement):
            if (i > 0):
                command += ','
            command += 'double *' + ',' + 'double *'
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(nbElement * 2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # GroupJogCurrentGet :  Get Jog current on selected group
    async def GroupJogCurrentGet(self, GroupName, nbElement):
        command = 'GroupJogCurrentGet(' + GroupName + ','
        for i in range(nbElement):
            if (i > 0):
                command += ','
            command += 'double *' + ',' + 'double *'
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(nbElement * 2):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # GroupJogModeEnable :  Enable Jog mode on selected group
    async def GroupJogModeEnable(self, GroupName):
        command = 'GroupJogModeEnable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupJogModeDisable :  Disable Jog mode on selected group
    async def GroupJogModeDisable(self, GroupName):
        command = 'GroupJogModeDisable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupKill :  Kill the group
    async def GroupKill(self, GroupName):
        command = 'GroupKill(' + GroupName + ')'
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

    # GroupMotionStatusGet :  Return group or positioner status
    async def GroupMotionStatusGet(self, GroupName, nbElement):
        command = 'GroupMotionStatusGet(' + GroupName + ','
        for i in range(nbElement):
            if (i > 0):
                command += ','
            command += 'int *'
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

    # GroupMoveAbort :  Abort a move
    async def GroupMoveAbort(self, GroupName):
        command = 'GroupMoveAbort(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupMoveAbortFast :  Abort quickly a move
    async def GroupMoveAbortFast(self, GroupName, AccelerationMultiplier):
        command = 'GroupMoveAbortFast(' + GroupName + \
            ',' + str(AccelerationMultiplier) + ')'
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

    # GroupPositionPCORawEncoderGet :  Return PCO raw encoder positions
    async def GroupPositionPCORawEncoderGet(self, GroupName, PositionX, PositionY):
        command = 'GroupPositionPCORawEncoderGet(' + GroupName + ',' + str(
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

    # GroupReferencingActionExecute :  Execute an action in referencing mode
    async def GroupReferencingActionExecute(self, PositionerName, ReferencingAction, ReferencingSensor, ReferencingParameter):
        command = 'GroupReferencingActionExecute(' + PositionerName + ',' + ReferencingAction + \
            ',' + ReferencingSensor + ',' + str(ReferencingParameter) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupReferencingStart :  Enter referencing mode
    async def GroupReferencingStart(self, GroupName):
        command = 'GroupReferencingStart(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupReferencingStop :  Exit referencing mode
    async def GroupReferencingStop(self, GroupName):
        command = 'GroupReferencingStop(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

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

    # GroupVelocityCurrentGet :  Return current velocities
    async def GroupVelocityCurrentGet(self, GroupName, nbElement):
        command = 'GroupVelocityCurrentGet(' + GroupName + ','
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

    # PositionerAnalogTrackingPositionParametersGet :  Read dynamic parameters
    # for one axe of a group for a future analog tracking position
    async def PositionerAnalogTrackingPositionParametersGet(self, PositionerName):
        command = 'PositionerAnalogTrackingPositionParametersGet(' + \
            PositionerName + ',char *,double *,double *,double *,double *)'
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

    # PositionerAnalogTrackingPositionParametersSet :  Update dynamic
    # parameters for one axe of a group for a future analog tracking position
    async def PositionerAnalogTrackingPositionParametersSet(self, PositionerName, GPIOName, Offset, Scale, Velocity, Acceleration):
        command = 'PositionerAnalogTrackingPositionParametersSet(' + PositionerName + ',' + GPIOName + ',' + str(
            Offset) + ',' + str(Scale) + ',' + str(Velocity) + ',' + str(Acceleration) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerAnalogTrackingVelocityParametersGet :  Read dynamic parameters
    # for one axe of a group for a future analog tracking velocity
    async def PositionerAnalogTrackingVelocityParametersGet(self, PositionerName):
        command = 'PositionerAnalogTrackingVelocityParametersGet(' + PositionerName + \
            ',char *,double *,double *,double *,int *,double *,double *)'
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

    # PositionerAnalogTrackingVelocityParametersSet :  Update dynamic
    # parameters for one axe of a group for a future analog tracking velocity
    async def PositionerAnalogTrackingVelocityParametersSet(self, PositionerName, GPIOName, Offset, Scale, DeadBandThreshold, Order, Velocity, Acceleration):
        command = 'PositionerAnalogTrackingVelocityParametersSet(' + PositionerName + ',' + GPIOName + ',' + str(Offset) + ',' + str(
            Scale) + ',' + str(DeadBandThreshold) + ',' + str(Order) + ',' + str(Velocity) + ',' + str(Acceleration) + ')'
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

    # PositionerCompensatedPCOAbort :  Abort CIE08 compensated PCO mode
    async def PositionerCompensatedPCOAbort(self, PositionerName):
        command = 'PositionerCompensatedPCOAbort(' + PositionerName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCompensatedPCOCurrentStatusGet :  Get current status of CIE08
    # compensated PCO mode
    async def PositionerCompensatedPCOCurrentStatusGet(self, PositionerName):
        command = 'PositionerCompensatedPCOCurrentStatusGet(' + \
            PositionerName + ',int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # PositionerCompensatedPCOEnable :  Enable CIE08 compensated PCO mode
    # execution
    async def PositionerCompensatedPCOEnable(self, PositionerName):
        command = 'PositionerCompensatedPCOEnable(' + PositionerName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCompensatedPCOFromFile :  Load file to CIE08 compensated PCO
    # data buffer
    async def PositionerCompensatedPCOFromFile(self, PositionerName, DataFileName):
        command = 'PositionerCompensatedPCOFromFile(' + \
            PositionerName + ',' + DataFileName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCompensatedPCOLoadToMemory :  Load data lines to CIE08
    # compensated PCO data buffer
    async def PositionerCompensatedPCOLoadToMemory(self, PositionerName, DataLines):
        command = 'PositionerCompensatedPCOLoadToMemory(' + \
            PositionerName + ',' + DataLines + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCompensatedPCOMemoryReset :  Reset CIE08 compensated PCO data
    # buffer
    async def PositionerCompensatedPCOMemoryReset(self, PositionerName):
        command = 'PositionerCompensatedPCOMemoryReset(' + PositionerName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCompensatedPCOPrepare :  Prepare data for CIE08 compensated
    # PCO mode
    async def PositionerCompensatedPCOPrepare(self, PositionerName, ScanDirection, StartPosition):
        command = 'PositionerCompensatedPCOPrepare(' + \
            PositionerName + ',' + ScanDirection + ','
        for i in range(len(StartPosition)):
            if (i > 0):
                command += ','
            command += str(StartPosition[i])
        command += ')'

        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCompensatedPCOSet :  Set data to CIE08 compensated PCO data
    # buffer
    async def PositionerCompensatedPCOSet(self, PositionerName, Start, Stop, Distance, Width):
        command = 'PositionerCompensatedPCOSet(' + PositionerName + ',' + str(
            Start) + ',' + str(Stop) + ',' + str(Distance) + ',' + str(Width) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCompensationFrequencyNotchsGet :  Read frequency compensation
    # notch filters parameters
    async def PositionerCompensationFrequencyNotchsGet(self, PositionerName):
        command = 'PositionerCompensationFrequencyNotchsGet(' + PositionerName + \
            ',double *,double *,double *,double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(9):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerCompensationFrequencyNotchsSet :  Update frequency
    # compensation notch filters parameters
    async def PositionerCompensationFrequencyNotchsSet(self, PositionerName, NotchFrequency1, NotchBandwidth1, NotchGain1, NotchFrequency2, NotchBandwidth2, NotchGain2, NotchFrequency3, NotchBandwidth3, NotchGain3):
        command = 'PositionerCompensationFrequencyNotchsSet(' + PositionerName + ',' + str(NotchFrequency1) + ',' + str(NotchBandwidth1) + ',' + str(NotchGain1) + ',' + str(
            NotchFrequency2) + ',' + str(NotchBandwidth2) + ',' + str(NotchGain2) + ',' + str(NotchFrequency3) + ',' + str(NotchBandwidth3) + ',' + str(NotchGain3) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCompensationLowPassTwoFilterGet :  Read second order low-pass
    # filter parameters
    async def PositionerCompensationLowPassTwoFilterGet(self, PositionerName):
        command = 'PositionerCompensationLowPassTwoFilterGet(' + \
            PositionerName + ',double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # PositionerCompensationLowPassTwoFilterSet :  Update second order
    # low-pass filter parameters
    async def PositionerCompensationLowPassTwoFilterSet(self, PositionerName, CutOffFrequency):
        command = 'PositionerCompensationLowPassTwoFilterSet(' + PositionerName + ',' + str(
            CutOffFrequency) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCompensationNotchModeFiltersGet :  Read notch mode filters
    # parameters
    async def PositionerCompensationNotchModeFiltersGet(self, PositionerName):
        command = 'PositionerCompensationNotchModeFiltersGet(' + PositionerName + \
            ',double *,double *,double *,double *,double *,double *,double *,double *)'
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

    # PositionerCompensationNotchModeFiltersSet :  Update notch mode filters
    # parameters
    async def PositionerCompensationNotchModeFiltersSet(self, PositionerName, NotchModeFr1, NotchModeFa1, NotchModeZr1, NotchModeZa1, NotchModeFr2, NotchModeFa2, NotchModeZr2, NotchModeZa2):
        command = 'PositionerCompensationNotchModeFiltersSet(' + PositionerName + ',' + str(NotchModeFr1) + ',' + str(NotchModeFa1) + ',' + str(
            NotchModeZr1) + ',' + str(NotchModeZa1) + ',' + str(NotchModeFr2) + ',' + str(NotchModeFa2) + ',' + str(NotchModeZr2) + ',' + str(NotchModeZa2) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCompensationPhaseCorrectionFiltersGet :  Read phase correction
    # filters parameters
    async def PositionerCompensationPhaseCorrectionFiltersGet(self, PositionerName):
        command = 'PositionerCompensationPhaseCorrectionFiltersGet(' + PositionerName + \
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

    # PositionerCompensationPhaseCorrectionFiltersSet :  Update phase
    # correction filters parameters
    async def PositionerCompensationPhaseCorrectionFiltersSet(self, PositionerName, PhaseCorrectionFn1, PhaseCorrectionFd1, PhaseCorrectionGain1, PhaseCorrectionFn2, PhaseCorrectionFd2, PhaseCorrectionGain2):
        command = 'PositionerCompensationPhaseCorrectionFiltersSet(' + PositionerName + ',' + str(PhaseCorrectionFn1) + ',' + str(PhaseCorrectionFd1) + ',' + str(
            PhaseCorrectionGain1) + ',' + str(PhaseCorrectionFn2) + ',' + str(PhaseCorrectionFd2) + ',' + str(PhaseCorrectionGain2) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCompensationSpatialPeriodicNotchsGet :  Read spatial
    # compensation notch filters parameters
    async def PositionerCompensationSpatialPeriodicNotchsGet(self, PositionerName):
        command = 'PositionerCompensationSpatialPeriodicNotchsGet(' + PositionerName + \
            ',double *,double *,double *,double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(9):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerCompensationSpatialPeriodicNotchsSet :  Update spatial
    # compensation notch filters parameters
    async def PositionerCompensationSpatialPeriodicNotchsSet(self, PositionerName, SpatialNotchStep1, SpatialNotchBandwidth1, SpatialNotchGain1, SpatialNotchStep2, SpatialNotchBandwidth2, SpatialNotchGain2, SpatialNotchStep3, SpatialNotchBandwidth3, SpatialNotchGain3):
        command = 'PositionerCompensationSpatialPeriodicNotchsSet(' + PositionerName + ',' + str(SpatialNotchStep1) + ',' + str(SpatialNotchBandwidth1) + ',' + str(SpatialNotchGain1) + ',' + str(
            SpatialNotchStep2) + ',' + str(SpatialNotchBandwidth2) + ',' + str(SpatialNotchGain2) + ',' + str(SpatialNotchStep3) + ',' + str(SpatialNotchBandwidth3) + ',' + str(SpatialNotchGain3) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorNotchFiltersSet :  Update filters parameters
    async def PositionerCorrectorNotchFiltersSet(self, PositionerName, NotchFrequency1, NotchBandwidth1, NotchGain1, NotchFrequency2, NotchBandwidth2, NotchGain2):
        command = 'PositionerCorrectorNotchFiltersSet(' + PositionerName + ',' + str(NotchFrequency1) + ',' + str(
            NotchBandwidth1) + ',' + str(NotchGain1) + ',' + str(NotchFrequency2) + ',' + str(NotchBandwidth2) + ',' + str(NotchGain2) + ')'
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

    # PositionerCorrectorPIDBaseSet :  Update PIDBase parameters
    async def PositionerCorrectorPIDBaseSet(self, PositionerName, MovingMass, StaticMass, Viscosity, Stiffness):
        command = 'PositionerCorrectorPIDBaseSet(' + PositionerName + ',' + str(
            MovingMass) + ',' + str(StaticMass) + ',' + str(Viscosity) + ',' + str(Stiffness) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorPIDBaseGet :  Read PIDBase parameters
    async def PositionerCorrectorPIDBaseGet(self, PositionerName):
        command = 'PositionerCorrectorPIDBaseGet(' + PositionerName + \
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

    # PositionerCorrectorPIDFFAccelerationSet :  Update corrector parameters
    async def PositionerCorrectorPIDFFAccelerationSet(self, PositionerName, ClosedLoopStatus, KP, KI, KD, KS, IntegrationTime, DerivativeFilterCutOffFrequency, GKP, GKI, GKD, KForm, KFeedForwardAcceleration, KFeedForwardJerk):
        command = 'PositionerCorrectorPIDFFAccelerationSet(' + PositionerName + ',' + str(ClosedLoopStatus) + ',' + str(KP) + ',' + str(KI) + ',' + str(KD) + ',' + str(KS) + ',' + str(IntegrationTime) + ',' + str(
            DerivativeFilterCutOffFrequency) + ',' + str(GKP) + ',' + str(GKI) + ',' + str(GKD) + ',' + str(KForm) + ',' + str(KFeedForwardAcceleration) + ',' + str(KFeedForwardJerk) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorPIDFFAccelerationGet :  Read corrector parameters
    async def PositionerCorrectorPIDFFAccelerationGet(self, PositionerName):
        command = 'PositionerCorrectorPIDFFAccelerationGet(' + PositionerName + \
            ',bool *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(13):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerCorrectorP2IDFFAccelerationSet :  Update corrector parameters
    async def PositionerCorrectorP2IDFFAccelerationSet(self, PositionerName, ClosedLoopStatus, KP, KI, KI2, KD, KS, IntegrationTime, DerivativeFilterCutOffFrequency, GKP, GKI, GKD, KForm, KFeedForwardAcceleration, KFeedForwardJerk, SetpointPositionDelay):
        command = 'PositionerCorrectorP2IDFFAccelerationSet(' + PositionerName + ',' + str(ClosedLoopStatus) + ',' + str(KP) + ',' + str(KI) + ',' + str(KI2) + ',' + str(KD) + ',' + str(KS) + ',' + str(IntegrationTime) + ',' + str(
            DerivativeFilterCutOffFrequency) + ',' + str(GKP) + ',' + str(GKI) + ',' + str(GKD) + ',' + str(KForm) + ',' + str(KFeedForwardAcceleration) + ',' + str(KFeedForwardJerk) + ',' + str(SetpointPositionDelay) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorP2IDFFAccelerationGet :  Read corrector parameters
    async def PositionerCorrectorP2IDFFAccelerationGet(self, PositionerName):
        command = 'PositionerCorrectorP2IDFFAccelerationGet(' + PositionerName + \
            ',bool *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(15):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerCorrectorPIDFFVelocitySet :  Update corrector parameters
    async def PositionerCorrectorPIDFFVelocitySet(self, PositionerName, ClosedLoopStatus, KP, KI, KD, KS, IntegrationTime, DerivativeFilterCutOffFrequency, GKP, GKI, GKD, KForm, KFeedForwardVelocity):
        command = 'PositionerCorrectorPIDFFVelocitySet(' + PositionerName + ',' + str(ClosedLoopStatus) + ',' + str(KP) + ',' + str(KI) + ',' + str(KD) + ',' + str(KS) + ',' + str(
            IntegrationTime) + ',' + str(DerivativeFilterCutOffFrequency) + ',' + str(GKP) + ',' + str(GKI) + ',' + str(GKD) + ',' + str(KForm) + ',' + str(KFeedForwardVelocity) + ')'
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
    async def PositionerCorrectorPIDDualFFVoltageSet(self, PositionerName, ClosedLoopStatus, KP, KI, KD, KS, IntegrationTime, DerivativeFilterCutOffFrequency, GKP, GKI, GKD, KForm, KFeedForwardVelocity, KFeedForwardAcceleration, Friction):
        command = 'PositionerCorrectorPIDDualFFVoltageSet(' + PositionerName + ',' + str(ClosedLoopStatus) + ',' + str(KP) + ',' + str(KI) + ',' + str(KD) + ',' + str(KS) + ',' + str(IntegrationTime) + ',' + str(
            DerivativeFilterCutOffFrequency) + ',' + str(GKP) + ',' + str(GKI) + ',' + str(GKD) + ',' + str(KForm) + ',' + str(KFeedForwardVelocity) + ',' + str(KFeedForwardAcceleration) + ',' + str(Friction) + ')'
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

    # PositionerCorrectorSR1AccelerationSet :  Update corrector parameters
    async def PositionerCorrectorSR1AccelerationSet(self, PositionerName, ClosedLoopStatus, KP, KI, KV, ObserverFrequency, CompensationGainVelocity, CompensationGainAcceleration, CompensationGainJerk):
        command = 'PositionerCorrectorSR1AccelerationSet(' + PositionerName + ',' + str(ClosedLoopStatus) + ',' + str(KP) + ',' + str(KI) + ',' + str(
            KV) + ',' + str(ObserverFrequency) + ',' + str(CompensationGainVelocity) + ',' + str(CompensationGainAcceleration) + ',' + str(CompensationGainJerk) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorSR1AccelerationGet :  Read corrector parameters
    async def PositionerCorrectorSR1AccelerationGet(self, PositionerName):
        command = 'PositionerCorrectorSR1AccelerationGet(' + PositionerName + \
            ',bool *,double *,double *,double *,double *,double *,double *,double *)'
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

    # PositionerCorrectorSR1ObserverAccelerationSet :  Update SR1 corrector
    # observer parameters
    async def PositionerCorrectorSR1ObserverAccelerationSet(self, PositionerName, ParameterA, ParameterB, ParameterC):
        command = 'PositionerCorrectorSR1ObserverAccelerationSet(' + PositionerName + ',' + str(
            ParameterA) + ',' + str(ParameterB) + ',' + str(ParameterC) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorSR1ObserverAccelerationGet :  Read SR1 corrector
    # observer parameters
    async def PositionerCorrectorSR1ObserverAccelerationGet(self, PositionerName):
        command = 'PositionerCorrectorSR1ObserverAccelerationGet(' + \
            PositionerName + ',double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerCorrectorSR1OffsetAccelerationSet :  Update SR1 corrector
    # output acceleration offset
    async def PositionerCorrectorSR1OffsetAccelerationSet(self, PositionerName, AccelerationOffset):
        command = 'PositionerCorrectorSR1OffsetAccelerationSet(' + PositionerName + ',' + str(
            AccelerationOffset) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerCorrectorSR1OffsetAccelerationGet :  Read SR1 corrector output
    # acceleration offset
    async def PositionerCorrectorSR1OffsetAccelerationGet(self, PositionerName):
        command = 'PositionerCorrectorSR1OffsetAccelerationGet(' + \
            PositionerName + ',double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

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

    # PositionerDriverFiltersGet :  Get driver filters parameters
    async def PositionerDriverFiltersGet(self, PositionerName):
        command = 'PositionerDriverFiltersGet(' + PositionerName + \
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

    # PositionerDriverFiltersSet :  Set driver filters parameters
    async def PositionerDriverFiltersSet(self, PositionerName, KI, NotchFrequency, NotchBandwidth, NotchGain, LowpassFrequency):
        command = 'PositionerDriverFiltersSet(' + PositionerName + ',' + str(KI) + ',' + str(
            NotchFrequency) + ',' + str(NotchBandwidth) + ',' + str(NotchGain) + ',' + str(LowpassFrequency) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerDriverPositionOffsetsGet :  Get driver stage and gage position
    # offset
    async def PositionerDriverPositionOffsetsGet(self, PositionerName):
        command = 'PositionerDriverPositionOffsetsGet(' + \
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

    # PositionerExcitationSignalGet :  Get excitation signal mode
    async def PositionerExcitationSignalGet(self, PositionerName):
        command = 'PositionerExcitationSignalGet(' + \
            PositionerName + ',int *,double *,double *,double *)'
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

    # PositionerExcitationSignalSet :  Set excitation signal mode
    async def PositionerExcitationSignalSet(self, PositionerName, Mode, Frequency, Amplitude, Time):
        command = 'PositionerExcitationSignalSet(' + PositionerName + ',' + str(
            Mode) + ',' + str(Frequency) + ',' + str(Amplitude) + ',' + str(Time) + ')'
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

    # PositionerHardInterpolatorPositionGet :  Read external latch position
    async def PositionerHardInterpolatorPositionGet(self, PositionerName):
        command = 'PositionerHardInterpolatorPositionGet(' + \
            PositionerName + ',double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

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

    # PositionerPositionCompareAquadBAlwaysEnable :  Enable AquadB signal in
    # always mode
    async def PositionerPositionCompareAquadBAlwaysEnable(self, PositionerName):
        command = 'PositionerPositionCompareAquadBAlwaysEnable(' + \
            PositionerName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerPositionCompareAquadBWindowedGet :  Read position compare
    # AquadB windowed parameters
    async def PositionerPositionCompareAquadBWindowedGet(self, PositionerName):
        command = 'PositionerPositionCompareAquadBWindowedGet(' + \
            PositionerName + ',double *,double *,bool *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerPositionCompareAquadBWindowedSet :  Set position compare
    # AquadB windowed parameters
    async def PositionerPositionCompareAquadBWindowedSet(self, PositionerName, MinimumPosition, MaximumPosition):
        command = 'PositionerPositionCompareAquadBWindowedSet(' + PositionerName + ',' + str(
            MinimumPosition) + ',' + str(MaximumPosition) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerPositionCompareGet :  Read position compare parameters
    async def PositionerPositionCompareGet(self, PositionerName):
        command = 'PositionerPositionCompareGet(' + PositionerName + \
            ',double *,double *,double *,bool *)'
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

    # PositionerPositionCompareSet :  Set position compare parameters
    async def PositionerPositionCompareSet(self, PositionerName, MinimumPosition, MaximumPosition, PositionStep):
        command = 'PositionerPositionCompareSet(' + PositionerName + ',' + str(
            MinimumPosition) + ',' + str(MaximumPosition) + ',' + str(PositionStep) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerPositionCompareEnable :  Enable position compare
    async def PositionerPositionCompareEnable(self, PositionerName):
        command = 'PositionerPositionCompareEnable(' + PositionerName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerPositionCompareDisable :  Disable position compare
    async def PositionerPositionCompareDisable(self, PositionerName):
        command = 'PositionerPositionCompareDisable(' + PositionerName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerPositionComparePulseParametersGet :  Get position compare PCO
    # pulse parameters
    async def PositionerPositionComparePulseParametersGet(self, PositionerName):
        command = 'PositionerPositionComparePulseParametersGet(' + \
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

    # PositionerPositionComparePulseParametersSet :  Set position compare PCO
    # pulse parameters
    async def PositionerPositionComparePulseParametersSet(self, PositionerName, PCOPulseWidth, EncoderSettlingTime):
        command = 'PositionerPositionComparePulseParametersSet(' + PositionerName + ',' + str(
            PCOPulseWidth) + ',' + str(EncoderSettlingTime) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerPositionCompareScanAccelerationLimitGet :  Get position
    # compare scan acceleration limit
    async def PositionerPositionCompareScanAccelerationLimitGet(self, PositionerName):
        command = 'PositionerPositionCompareScanAccelerationLimitGet(' + \
            PositionerName + ',double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # PositionerPositionCompareScanAccelerationLimitSet :  Set position
    # compare scan acceleration limit
    async def PositionerPositionCompareScanAccelerationLimitSet(self, PositionerName, ScanAccelerationLimit):
        command = 'PositionerPositionCompareScanAccelerationLimitSet(' + PositionerName + ',' + str(
            ScanAccelerationLimit) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerPreCorrectorExcitationSignalGet :  Get pre-corrector
    # excitation signal mode
    async def PositionerPreCorrectorExcitationSignalGet(self, PositionerName):
        command = 'PositionerPreCorrectorExcitationSignalGet(' + \
            PositionerName + ',double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerPreCorrectorExcitationSignalSet :  Set pre-corrector
    # excitation signal mode
    async def PositionerPreCorrectorExcitationSignalSet(self, PositionerName, Frequency, Amplitude, Time):
        command = 'PositionerPreCorrectorExcitationSignalSet(' + PositionerName + ',' + str(
            Frequency) + ',' + str(Amplitude) + ',' + str(Time) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerRawEncoderPositionGet :  Get the raw encoder position
    async def PositionerRawEncoderPositionGet(self, PositionerName, UserEncoderPosition):
        command = 'PositionerRawEncoderPositionGet(' + PositionerName + ',' + str(
            UserEncoderPosition) + ',double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # PositionersEncoderIndexDifferenceGet :  Return the difference between
    # index of primary axis and secondary axis (only after homesearch)
    async def PositionersEncoderIndexDifferenceGet(self, PositionerName):
        command = 'PositionersEncoderIndexDifferenceGet(' + \
            PositionerName + ',double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

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

    # PositionerTimeFlasherGet :  Read time flasher parameters
    async def PositionerTimeFlasherGet(self, PositionerName):
        command = 'PositionerTimeFlasherGet(' + PositionerName + \
            ',double *,double *,double *,bool *)'
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

    # PositionerTimeFlasherSet :  Set time flasher parameters
    async def PositionerTimeFlasherSet(self, PositionerName, MinimumPosition, MaximumPosition, TimeInterval):
        command = 'PositionerTimeFlasherSet(' + PositionerName + ',' + str(
            MinimumPosition) + ',' + str(MaximumPosition) + ',' + str(TimeInterval) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerTimeFlasherEnable :  Enable time flasher
    async def PositionerTimeFlasherEnable(self, PositionerName):
        command = 'PositionerTimeFlasherEnable(' + PositionerName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerTimeFlasherDisable :  Disable time flasher
    async def PositionerTimeFlasherDisable(self, PositionerName):
        command = 'PositionerTimeFlasherDisable(' + PositionerName + ')'
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

    # PositionerWarningFollowingErrorSet :  Set positioner warning following
    # error limit
    async def PositionerWarningFollowingErrorSet(self, PositionerName, WarningFollowingError):
        command = 'PositionerWarningFollowingErrorSet(' + PositionerName + ',' + str(
            WarningFollowingError) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerWarningFollowingErrorGet :  Get positioner warning following
    # error limit
    async def PositionerWarningFollowingErrorGet(self, PositionerName):
        command = 'PositionerWarningFollowingErrorGet(' + \
            PositionerName + ',double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # PositionerCorrectorAutoTuning :  Astrom&Hagglund based auto-tuning
    async def PositionerCorrectorAutoTuning(self, PositionerName, TuningMode):
        command = 'PositionerCorrectorAutoTuning(' + PositionerName + ',' + str(
            TuningMode) + ',double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # PositionerAccelerationAutoScaling :  Astrom&Hagglund based auto-scaling
    async def PositionerAccelerationAutoScaling(self, PositionerName):
        command = 'PositionerAccelerationAutoScaling(' + \
            PositionerName + ',double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # MultipleAxesPVTVerification :  Multiple axes PVT trajectory verification
    async def MultipleAxesPVTVerification(self, GroupName, TrajectoryFileName):
        command = 'MultipleAxesPVTVerification(' + \
            GroupName + ',' + TrajectoryFileName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # MultipleAxesPVTVerificationResultGet :  Multiple axes PVT trajectory
    # verification result get
    async def MultipleAxesPVTVerificationResultGet(self, PositionerName):
        command = 'MultipleAxesPVTVerificationResultGet(' + PositionerName + \
            ',char *,double *,double *,double *,double *)'
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

    # MultipleAxesPVTExecution :  Multiple axes PVT trajectory execution
    async def MultipleAxesPVTExecution(self, GroupName, TrajectoryFileName, ExecutionNumber):
        command = 'MultipleAxesPVTExecution(' + GroupName + ',' + \
            TrajectoryFileName + ',' + str(ExecutionNumber) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # MultipleAxesPVTParametersGet :  Multiple axes PVT trajectory get
    # parameters
    async def MultipleAxesPVTParametersGet(self, GroupName):
        command = 'MultipleAxesPVTParametersGet(' + \
            GroupName + ',char *,int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # MultipleAxesPVTPulseOutputSet :  Configure pulse output on trajectory
    async def MultipleAxesPVTPulseOutputSet(self, GroupName, StartElement, EndElement, TimeInterval):
        command = 'MultipleAxesPVTPulseOutputSet(' + GroupName + ',' + str(
            StartElement) + ',' + str(EndElement) + ',' + str(TimeInterval) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # MultipleAxesPVTPulseOutputGet :  Get pulse output on trajectory
    # configuration
    async def MultipleAxesPVTPulseOutputGet(self, GroupName):
        command = 'MultipleAxesPVTPulseOutputGet(' + \
            GroupName + ',int *,int *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # MultipleAxesPVTLoadToMemory :  Multiple Axes Load PVT trajectory through
    # function
    async def MultipleAxesPVTLoadToMemory(self, GroupName, TrajectoryPart):
        command = 'MultipleAxesPVTLoadToMemory(' + \
            GroupName + ',' + TrajectoryPart + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # MultipleAxesPVTResetInMemory :  Multiple Axes PVT trajectory reset in
    # memory
    async def MultipleAxesPVTResetInMemory(self, GroupName):
        command = 'MultipleAxesPVTResetInMemory(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SingleAxisSlaveModeEnable :  Enable the slave mode
    async def SingleAxisSlaveModeEnable(self, GroupName):
        command = 'SingleAxisSlaveModeEnable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SingleAxisSlaveModeDisable :  Disable the slave mode
    async def SingleAxisSlaveModeDisable(self, GroupName):
        command = 'SingleAxisSlaveModeDisable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SingleAxisSlaveParametersSet :  Set slave parameters
    async def SingleAxisSlaveParametersSet(self, GroupName, PositionerName, Ratio):
        command = 'SingleAxisSlaveParametersSet(' + GroupName + \
            ',' + PositionerName + ',' + str(Ratio) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SingleAxisSlaveParametersGet :  Get slave parameters
    async def SingleAxisSlaveParametersGet(self, GroupName):
        command = 'SingleAxisSlaveParametersGet(' + \
            GroupName + ',char *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # SingleAxisThetaClampDisable :  Set clamping disable on selected group
    async def SingleAxisThetaClampDisable(self, GroupName):
        command = 'SingleAxisThetaClampDisable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SingleAxisThetaClampEnable :  Set clamping enable on selected group
    async def SingleAxisThetaClampEnable(self, GroupName):
        command = 'SingleAxisThetaClampEnable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SingleAxisThetaSlaveModeEnable :  Enable the slave mode
    async def SingleAxisThetaSlaveModeEnable(self, GroupName):
        command = 'SingleAxisThetaSlaveModeEnable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SingleAxisThetaSlaveModeDisable :  Disable the slave mode
    async def SingleAxisThetaSlaveModeDisable(self, GroupName):
        command = 'SingleAxisThetaSlaveModeDisable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SingleAxisThetaSlaveParametersSet :  Set slave parameters
    async def SingleAxisThetaSlaveParametersSet(self, GroupName, PositionerName, Ratio):
        command = 'SingleAxisThetaSlaveParametersSet(' + GroupName + \
            ',' + PositionerName + ',' + str(Ratio) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SingleAxisThetaSlaveParametersGet :  Get slave parameters
    async def SingleAxisThetaSlaveParametersGet(self, GroupName):
        command = 'SingleAxisThetaSlaveParametersGet(' + \
            GroupName + ',char *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # SpindleSlaveModeEnable :  Enable the slave mode
    async def SpindleSlaveModeEnable(self, GroupName):
        command = 'SpindleSlaveModeEnable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SpindleSlaveModeDisable :  Disable the slave mode
    async def SpindleSlaveModeDisable(self, GroupName):
        command = 'SpindleSlaveModeDisable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SpindleSlaveParametersSet :  Set slave parameters
    async def SpindleSlaveParametersSet(self, GroupName, PositionerName, Ratio):
        command = 'SpindleSlaveParametersSet(' + GroupName + \
            ',' + PositionerName + ',' + str(Ratio) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SpindleSlaveParametersGet :  Get slave parameters
    async def SpindleSlaveParametersGet(self, GroupName):
        command = 'SpindleSlaveParametersGet(' + \
            GroupName + ',char *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # GroupSpinParametersSet :  Modify Spin parameters on selected group and
    # activate the continuous move
    async def GroupSpinParametersSet(self, GroupName, Velocity, Acceleration):
        command = 'GroupSpinParametersSet(' + GroupName + \
            ',' + str(Velocity) + ',' + str(Acceleration) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # GroupSpinParametersGet :  Get Spin parameters on selected group
    async def GroupSpinParametersGet(self, GroupName):
        command = 'GroupSpinParametersGet(' + GroupName + ',double *,double *)'
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

    # GroupSpinCurrentGet :  Get Spin current on selected group
    async def GroupSpinCurrentGet(self, GroupName):
        command = 'GroupSpinCurrentGet(' + GroupName + ',double *,double *)'
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

    # GroupSpinModeStop :  Stop Spin mode on selected group with specified
    # acceleration
    async def GroupSpinModeStop(self, GroupName, Acceleration):
        command = 'GroupSpinModeStop(' + GroupName + \
            ',' + str(Acceleration) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # XYLineArcVerification :  XY trajectory verification
    async def XYLineArcVerification(self, GroupName, TrajectoryFileName):
        command = 'XYLineArcVerification(' + \
            GroupName + ',' + TrajectoryFileName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # XYLineArcVerificationResultGet :  XY trajectory verification result get
    async def XYLineArcVerificationResultGet(self, PositionerName):
        command = 'XYLineArcVerificationResultGet(' + PositionerName + \
            ',char *,double *,double *,double *,double *)'
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

    # XYLineArcExecution :  XY trajectory execution
    async def XYLineArcExecution(self, GroupName, TrajectoryFileName, Velocity, Acceleration, ExecutionNumber):
        command = 'XYLineArcExecution(' + GroupName + ',' + TrajectoryFileName + ',' + str(
            Velocity) + ',' + str(Acceleration) + ',' + str(ExecutionNumber) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # XYLineArcParametersGet :  XY trajectory get parameters
    async def XYLineArcParametersGet(self, GroupName):
        command = 'XYLineArcParametersGet(' + GroupName + \
            ',char *,double *,double *,int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # XYLineArcPulseOutputSet :  Configure pulse output on trajectory
    async def XYLineArcPulseOutputSet(self, GroupName, StartLength, EndLength, PathLengthInterval):
        command = 'XYLineArcPulseOutputSet(' + GroupName + ',' + str(
            StartLength) + ',' + str(EndLength) + ',' + str(PathLengthInterval) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # XYLineArcPulseOutputGet :  Get pulse output on trajectory configuration
    async def XYLineArcPulseOutputGet(self, GroupName):
        command = 'XYLineArcPulseOutputGet(' + \
            GroupName + ',double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # XYPVTVerification :  XY PVT trajectory verification
    async def XYPVTVerification(self, GroupName, TrajectoryFileName):
        command = 'XYPVTVerification(' + GroupName + \
            ',' + TrajectoryFileName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # XYPVTVerificationResultGet :  XY PVT trajectory verification result get
    async def XYPVTVerificationResultGet(self, PositionerName):
        command = 'XYPVTVerificationResultGet(' + PositionerName + \
            ',char *,double *,double *,double *,double *)'
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

    # XYPVTExecution :  XY PVT trajectory execution
    async def XYPVTExecution(self, GroupName, TrajectoryFileName, ExecutionNumber):
        command = 'XYPVTExecution(' + GroupName + ',' + \
            TrajectoryFileName + ',' + str(ExecutionNumber) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # XYPVTParametersGet :  XY PVT trajectory get parameters
    async def XYPVTParametersGet(self, GroupName):
        command = 'XYPVTParametersGet(' + GroupName + ',char *,int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # XYPVTPulseOutputSet :  Configure pulse output on trajectory
    async def XYPVTPulseOutputSet(self, GroupName, StartElement, EndElement, TimeInterval):
        command = 'XYPVTPulseOutputSet(' + GroupName + ',' + str(
            StartElement) + ',' + str(EndElement) + ',' + str(TimeInterval) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # XYPVTPulseOutputGet :  Get pulse output on trajectory configuration
    async def XYPVTPulseOutputGet(self, GroupName):
        command = 'XYPVTPulseOutputGet(' + GroupName + ',int *,int *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # XYPVTLoadToMemory :  XY Load PVT trajectory through function
    async def XYPVTLoadToMemory(self, GroupName, TrajectoryPart):
        command = 'XYPVTLoadToMemory(' + GroupName + ',' + TrajectoryPart + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # XYPVTResetInMemory :  XY PVT trajectory reset in memory
    async def XYPVTResetInMemory(self, GroupName):
        command = 'XYPVTResetInMemory(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # XYZGroupPositionCorrectedProfilerGet :  Return corrected profiler
    # positions
    async def XYZGroupPositionCorrectedProfilerGet(self, GroupName, PositionX, PositionY, PositionZ):
        command = 'XYZGroupPositionCorrectedProfilerGet(' + GroupName + ',' + str(
            PositionX) + ',' + str(PositionY) + ',' + str(PositionZ) + ',double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # XYZGroupPositionPCORawEncoderGet :  Return PCO raw encoder positions
    async def XYZGroupPositionPCORawEncoderGet(self, GroupName, PositionX, PositionY, PositionZ):
        command = 'XYZGroupPositionPCORawEncoderGet(' + GroupName + ',' + str(
            PositionX) + ',' + str(PositionY) + ',' + str(PositionZ) + ',double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # XYZSplineVerification :  XYZ trajectory verifivation
    async def XYZSplineVerification(self, GroupName, TrajectoryFileName):
        command = 'XYZSplineVerification(' + \
            GroupName + ',' + TrajectoryFileName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # XYZSplineVerificationResultGet :  XYZ trajectory verification result get
    async def XYZSplineVerificationResultGet(self, PositionerName):
        command = 'XYZSplineVerificationResultGet(' + PositionerName + \
            ',char *,double *,double *,double *,double *)'
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

    # XYZSplineExecution :  XYZ trajectory execution
    async def XYZSplineExecution(self, GroupName, TrajectoryFileName, Velocity, Acceleration):
        command = 'XYZSplineExecution(' + GroupName + ',' + TrajectoryFileName + \
            ',' + str(Velocity) + ',' + str(Acceleration) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # XYZSplineParametersGet :  XYZ trajectory get parameters
    async def XYZSplineParametersGet(self, GroupName):
        command = 'XYZSplineParametersGet(' + GroupName + \
            ',char *,double *,double *,int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # TZPVTVerification :  TZ PVT trajectory verification
    async def TZPVTVerification(self, GroupName, TrajectoryFileName):
        command = 'TZPVTVerification(' + GroupName + \
            ',' + TrajectoryFileName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TZPVTVerificationResultGet :  TZ PVT trajectory verification result get
    async def TZPVTVerificationResultGet(self, PositionerName):
        command = 'TZPVTVerificationResultGet(' + PositionerName + \
            ',char *,double *,double *,double *,double *)'
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

    # TZPVTExecution :  TZ PVT trajectory execution
    async def TZPVTExecution(self, GroupName, TrajectoryFileName, ExecutionNumber):
        command = 'TZPVTExecution(' + GroupName + ',' + \
            TrajectoryFileName + ',' + str(ExecutionNumber) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TZPVTParametersGet :  TZ PVT trajectory get parameters
    async def TZPVTParametersGet(self, GroupName):
        command = 'TZPVTParametersGet(' + GroupName + ',char *,int *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # TZPVTPulseOutputSet :  Configure pulse output on trajectory
    async def TZPVTPulseOutputSet(self, GroupName, StartElement, EndElement, TimeInterval):
        command = 'TZPVTPulseOutputSet(' + GroupName + ',' + str(
            StartElement) + ',' + str(EndElement) + ',' + str(TimeInterval) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TZPVTPulseOutputGet :  Get pulse output on trajectory configuration
    async def TZPVTPulseOutputGet(self, GroupName):
        command = 'TZPVTPulseOutputGet(' + GroupName + ',int *,int *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # TZPVTLoadToMemory :  TZ Load PVT trajectory through function
    async def TZPVTLoadToMemory(self, GroupName, TrajectoryPart):
        command = 'TZPVTLoadToMemory(' + GroupName + ',' + TrajectoryPart + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TZPVTResetInMemory :  TZ PVT trajectory reset in memory
    async def TZPVTResetInMemory(self, GroupName):
        command = 'TZPVTResetInMemory(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TZFocusModeEnable :  Enable the focus mode
    async def TZFocusModeEnable(self, GroupName):
        command = 'TZFocusModeEnable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TZFocusModeDisable :  Disable the focus mode
    async def TZFocusModeDisable(self, GroupName):
        command = 'TZFocusModeDisable(' + GroupName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TZTrackingUserMaximumZZZTargetDifferenceGet :  Get user maximum ZZZ
    # target difference for tracking control
    async def TZTrackingUserMaximumZZZTargetDifferenceGet(self, GroupName):
        command = 'TZTrackingUserMaximumZZZTargetDifferenceGet(' + \
            GroupName + ',double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
            j += 1
        retList.append(eval(returnedString[i:i + j]))

        return retList

    # TZTrackingUserMaximumZZZTargetDifferenceSet :  Set user maximum ZZZ
    # target difference for tracking control
    async def TZTrackingUserMaximumZZZTargetDifferenceSet(self, GroupName, UserMaximumZZZTargetDifference):
        command = 'TZTrackingUserMaximumZZZTargetDifferenceSet(' + GroupName + ',' + str(
            UserMaximumZZZTargetDifference) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # FocusProcessSocketReserve :  Set user maximum ZZZ target difference for
    # tracking control
    async def FocusProcessSocketReserve(self):
        command = 'FocusProcessSocketReserve()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # FocusProcessSocketFree :  Set user maximum ZZZ target difference for
    # tracking control
    async def FocusProcessSocketFree(self):
        command = 'FocusProcessSocketFree()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # PositionerMotorOutputOffsetGet :  Get soft (user defined) motor output
    # DAC offsets
    async def PositionerMotorOutputOffsetGet(self, PositionerName):
        command = 'PositionerMotorOutputOffsetGet(' + PositionerName + \
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

    # PositionerMotorOutputOffsetSet :  Set soft (user defined) motor output
    # DAC offsets
    async def PositionerMotorOutputOffsetSet(self, PositionerName, PrimaryDAC1, PrimaryDAC2, SecondaryDAC1, SecondaryDAC2):
        command = 'PositionerMotorOutputOffsetSet(' + PositionerName + ',' + str(PrimaryDAC1) + ',' + str(
            PrimaryDAC2) + ',' + str(SecondaryDAC1) + ',' + str(SecondaryDAC2) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # SingleAxisThetaPositionRawGet :  Get raw encoder positions for single
    # axis theta encoder
    async def SingleAxisThetaPositionRawGet(self, GroupName):
        command = 'SingleAxisThetaPositionRawGet(' + \
            GroupName + ',double *,double *,double *)'
        (error, returnedString) = await self._sendAndReceive(command)
        if (error != 0):
            return (error, returnedString)

        i, j, retList = 0, 0, [error]
        for paramNb in range(3):
            while ((i + j) < len(returnedString) and returnedString[i + j] != ','):
                j += 1
            retList.append(eval(returnedString[i:i + j]))
            i, j = i + j + 1, 0

        return retList

    # EEPROMCIESet :  Get raw encoder positions for single axis theta encoder
    async def EEPROMCIESet(self, CardNumber, ReferenceString):
        command = 'EEPROMCIESet(' + str(CardNumber) + \
            ',' + ReferenceString + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EEPROMDACOffsetCIESet :  Get raw encoder positions for single axis theta
    # encoder
    async def EEPROMDACOffsetCIESet(self, PlugNumber, DAC1Offset, DAC2Offset):
        command = 'EEPROMDACOffsetCIESet(' + str(PlugNumber) + \
            ',' + str(DAC1Offset) + ',' + str(DAC2Offset) + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EEPROMDriverSet :  Get raw encoder positions for single axis theta
    # encoder
    async def EEPROMDriverSet(self, PlugNumber, ReferenceString):
        command = 'EEPROMDriverSet(' + str(PlugNumber) + \
            ',' + ReferenceString + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # EEPROMINTSet :  Get raw encoder positions for single axis theta encoder
    async def EEPROMINTSet(self, CardNumber, ReferenceString):
        command = 'EEPROMINTSet(' + str(CardNumber) + \
            ',' + ReferenceString + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # CPUCoreAndBoardSupplyVoltagesGet :  Get raw encoder positions for single
    # axis theta encoder
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

    # CPUTemperatureAndFanSpeedGet :  Get raw encoder positions for single
    # axis theta encoder
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

    # ControllerStatusListGet :  Controller status list
    async def ControllerStatusListGet(self):
        command = 'ControllerStatusListGet(char *)'
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

    # PrepareForUpdate :  Prepare for update controller
    async def PrepareForUpdate(self):
        command = 'PrepareForUpdate()'
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

    # ControllerMotionKernelMinMaxTimeLoadGet :  Get controller motion kernel
    # minimum and maximum time load
    async def ControllerMotionKernelMinMaxTimeLoadGet(self):
        command = 'ControllerMotionKernelMinMaxTimeLoadGet(double *,double *,double *,double *,double *,double *,double *,double *)'
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

    # ControllerMotionKernelMinMaxTimeLoadReset :  Reset controller motion
    # kernel min/max time load
    async def ControllerMotionKernelMinMaxTimeLoadReset(self):
        command = 'ControllerMotionKernelMinMaxTimeLoadReset()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

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

    # SocketsStatusGet :  Get sockets current status
    async def SocketsStatusGet(self):
        command = 'SocketsStatusGet(char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # TestTCP :  Test TCP/IP transfert
    async def TestTCP(self, InputString):
        command = 'TestTCP(' + InputString + ',char *)'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # ISRCorrectorCompensateOverrunNumberGet :  Get ISR Corrector Compensate
    # Overrun Number
    async def ISRCorrectorCompensateOverrunNumberGet(self):
        command = 'ISRCorrectorCompensateOverrunNumberGet(int *,int *)'
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

    # ISRCorrectorCompensateOverrunNumberReset :  Reset ISR Corrector
    # Compensate Overrun Number
    async def ISRCorrectorCompensateOverrunNumberReset(self):
        command = 'ISRCorrectorCompensateOverrunNumberReset()'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # OptionalModuleExecute :  Execute an optional module
    async def OptionalModuleExecute(self, ModuleFileName):
        command = 'OptionalModuleExecute(' + ModuleFileName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)

    # OptionalModuleKill :  Kill an optional module
    async def OptionalModuleKill(self, TaskName):
        command = 'OptionalModuleKill(' + TaskName + ')'
        (error, returnedString) = await self._sendAndReceive(command)
        return (error, returnedString)
