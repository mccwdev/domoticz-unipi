# -*- coding: utf-8 -*-
#
# UniPi Plugin for Domoticz
#
# Manage and monitor your UniPi controller from Domoticz. This plugin imports all available inputs, 1Wire sensors
# and relay outputs.
#
# Communication is done via the UniPi EVOK API. Tested and developed on UniPi Neuron L203.
#
# © 2019 March - mccwdev <https://github.com/mccwdev/>
#

"""
<plugin key="UniPi" name="UniPi EVOK" author="mccwdev" version="1.0.0"
wikilink="https://www.domoticz.com/wiki/Using_Python_plugins" externallink="https://github.com/mccwdev/domoticz-unipi">
    <description>
        <h2>UniPi Plugin</h2><br/>
        Manage your UniPi with Domoticz using the Api from EVOK control software
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>Import inputs, relays and external sensors</li>
            <li>Control relays from Domoticz</li>
            <li>Read and log input and external sensor data</li>
        </ul>
        <h3>Devices</h3>
        <ul style="list-style-type:square">
            <li>Tested on UniPi Neuron L203</li>
        </ul>
    </description>
    <params>
    <param field="Address" label="IP Address" width="200px" required="true" default="127.0.0.1"/>
    <param field="Port" label="Port" width="30px" required="true" default="8080"/>
    <param field="Mode1" label="Debug" width="75px">
         <options>
            <option label="True" value="Debug"/>
            <option label="False" value="Normal"  default="true" />
         </options>
      </param>
    </params>
</plugin>
"""

import json
import requests
try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode
import Domoticz


TIMEOUT_REQUESTS = 3
UNIPI_DEVICES = {  # Tuple with (Name, Type, SubType, SwitchType), Type=0 means not supported
    'input': ('Input',           244,    62,     0),
    'temp':  ('Temp',             80,     5,     0),
    'relay': ('Relay',           244,    73,     2),
    'ai':    ('Analog Input',    243,     8,     0),
    'ao':    ('Analog Output',   244,    62,     7),
    'led':   ('ULED',            244,    73,    18),
    'wd':    ('Watch Dog',         0,     0,     0),
    'neuro': ('Evok Devices',      0,     0,     0),
    'uart':  ('UART Serial Port',  0,     0,     0)
}


class BasePlugin:
    enabled = True
    unipi_url = ''

    def __init__(self):
        return

    def request(self, url_path, variables=None, method='get'):
        url_vars = ''
        url = self.unipi_url + url_path
        Domoticz.Debug("Url request %s" % url)
        resp = None
        if method == 'get':
            if variables is None:
                variables = {}
            if variables:
                url_vars = '?' + urlencode(variables)
            url += url_vars
            try:
                resp = requests.get(url, timeout=TIMEOUT_REQUESTS)
            except Exception as err:
                Domoticz.Error("Could not connect to url url %s: %s" % (url, err))
                return dict()
        elif method == 'post':
            resp = requests.post(url, json=dict(variables), timeout=TIMEOUT_REQUESTS)
        if not(resp.status_code == 200 or resp.status_code == 201):
            Domoticz.Error("Could not connect to url %s, response %d" % (url, resp.status_code))
            return dict()
        return json.loads(resp.text)

    def onStart(self):
        self.unipi_url = "http://" + Parameters["Address"] + ":" + Parameters["Port"]
        Domoticz.Log("Connect to UniPi EVOK API on URL %s" % self.unipi_url)
        if Parameters["Mode1"] == "Debug":
            Domoticz.Debugging(1)

        if not len(Devices):
            dev_id = 1
            data = self.request("/rest/all")
            for device in data:
                unipi_dev_id = device["circuit"]
                dev_tpl = UNIPI_DEVICES[device["dev"]]
                if dev_tpl[1] == 0:
                    Domoticz.Log("Device type %s (%s) not supported" % (device["dev"], unipi_dev_id))
                else:
                    dev_name = dev_tpl[0] + ' ' + unipi_dev_id
                    Domoticz.Device(Name=dev_name, Unit=dev_id, Type=dev_tpl[1], Subtype=dev_tpl[2],
                                    Switchtype=dev_tpl[3], DeviceID=unipi_dev_id).Create()
                dev_id += 1
        Domoticz.Heartbeat(2)
        return True

    def onStop(self):
        Domoticz.Log("onStop called")

    def onConnect(self, Connection, Status, Description):
        Domoticz.Log("onConnect called")

    def onMessage(self, Connection, Data):
        Domoticz.Log("onMessage called")

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))
        unipi_dev_id = Devices[Unit].DeviceID
        value = 0 if Command == 'Off' else 1
        Domoticz.Log("Command %s for device %s" % (Command, unipi_dev_id))
        if self.request('/rest/relay/' + unipi_dev_id, {'value': str(value)}):
            UpdateDevice(Unit, value, Command)

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Log("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Log("onDisconnect called")

    def onHeartbeat(self):
        data = self.request("/rest/all")
        for device in data:
            if device["dev"] not in ["input", "temp"]:
                continue  # Skip outputs and unsupported devices
            device_id = self.getDeviceID(device['circuit'])
            if not device_id:
                if device["dev"] == 'temp':
                    device_id = max([id for (id, dev) in Devices.items()]) + 1
                    Domoticz.Device(Name="Temp " + str(device_id), Unit=device_id, TypeName="Temperature",
                                    DeviceID=device['circuit']).Create()
                else:
                    continue
            if device["dev"] in ["input", "temp"]:
                if device["value"] is None or device["value"] == 'null':
                    Domoticz.Log("No value from device %s (%s)" % (device['circuit'], device_id))
                    continue
                value_str = str(device["value"])
                value_int = int(round(device["value"]))
                if value_str != Devices[device_id].sValue or value_int != Devices[device_id].nValue:
                    UpdateDevice(device_id, value_int, value_str)
        # TODO: Update names from Domo to UniPi

    def getDeviceID(self, unipi_dev_id, input_device=True):
        if input_device:
            dev_list = [id for (id, dev) in Devices.items() if dev.DeviceID == unipi_dev_id and dev.SubType != 73]
        else:
            dev_list = [id for (id, dev) in Devices.items() if dev.DeviceID == unipi_dev_id and dev.SubType == 73]
        if not dev_list:
            Domoticz.Log("Device with ID %s not found!" % unipi_dev_id)
            return
        elif len(dev_list) > 1:
            Domoticz.Log("Multiple devices with ID %s found, cannot update!" % unipi_dev_id)
            return
        return dev_list[0]


_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)


def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)


def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)


def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)


def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()


    # Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return


def UpdateDevice(Unit, nValue, sValue=''):
    # Make sure that the Domoticz device still exists (they can be deleted) before updating it
    if Unit in Devices:
        if (Devices[Unit].nValue != nValue) or (Devices[Unit].sValue != sValue):
            Devices[Unit].Update(nValue=nValue, sValue=str(sValue))
            Domoticz.Log("Update %s, value %s" % (Devices[Unit].Name, sValue))
    return
