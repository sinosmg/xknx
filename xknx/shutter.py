from .address import Address
from .multicast import Multicast
from .telegram import Telegram
from .device import Device
from .address import Address
from .travelcalculator import TravelCalculator
from .globals import Globals

class CouldNotParseShutterTelegram(Exception):
    pass

class Shutter(Device):
    def __init__(self, name, config):
        Device.__init__(self, name)
        self.group_address_long = Address(config.get("group_address_long"))
        self.group_address_short = Address(config.get("group_address_short"))
        self.group_address_position = Address(config.get("group_address_position"))
        self.group_address_position_feedback = Address(config.get("group_address_position_feedback"))

        self.travelcalculator = TravelCalculator(100,100) #todo set travel times from configuration

    def has_group_address(self, group_address):
        return ( self.group_address_long == group_address ) or (self.group_address_short == group_address ) or (self.group_address_position_feedback == group_address )


    def __str__(self):
        return "<Shutter group_address_long={0}, group_address_short={1}, group_address_position, group_address_position_feedback={2}, name={3}>".format(self.group_address_long,self.group_address_short,self.group_address_position, self.group_address_position_feedback,self.name)

    def send(self, group_address, payload):
        multicast = Multicast()
        telegram = Telegram()
        telegram.sender = Globals.get_own_address()
        telegram.group_address=group_address

        if isinstance(payload, list):
            for p in payload:
                telegram.payload.append(p)
        elif isinstance(payload, int):
                telegram.payload.append(payload)
        else:
            print("Cannot understand payload")

        multicast.send(telegram)

    def set_down(self):
        if not self.group_address_long.is_set():
            print("group_address_long not defined for device {0}".format(self.get_name()))
            return
        self.send(self.group_address_long, 0x81)
        self.travelcalculator.start_travel_down()

    def set_up(self):
        if not self.group_address_long.is_set():
            print("group_address_long not defined for device {0}".format(self.get_name()))
            return
        self.send(self.group_address_long, 0x80)
        self.travelcalculator.start_travel_up()

    def set_short_down(self):
        if not self.group_address_short.is_set():
            print("group_address_short not defined for device {0}".format(self.get_name()))
            return
        self.send(self.group_address_short, 0x81)

    def set_short_up(self):
        if not self.group_address_short.is_set():
            print("group_address_short not defined for device {0}".format(self.get_name()))
            return
        self.send(self.group_address_short, 0x80)

    def stop(self):
        # Thats the KNX way of doing this. electrical engineers ... m-)
        self.set_short_down()
        self.travelcalculator.stop()

    def set_position(self, position):
        if not self.group_address_position.is_set():
            print("group_address_position not defined for device {0}".format(self.get_name()))
            return
        self.send(self.group_address_position, [0x80, position])
        self.travelcalculator.start_travel( position )

    def do(self,action):
        if(action=="up"):
            self.set_up()
        elif(action=="short_up"):
            self.set_short_up()
        elif(action=="down"):
            self.set_down()
        elif(action=="short_down"):
            self.set_short_down()        
        else:
            print("{0}: Could not understand action {1}".format(self.get_name(), action))

    def request_state(self):
        if not self.group_address_position_feedback.is_set():
            print("group_position not defined for device {0}".format(self.get_name()))
            return
        if self.travelcalculator.is_travelling():
            # Cover is travelling, requesting state will return false results
            return
        self.send(self.group_address_position_feedback,0x00)

    def process(self,telegram):
        if len(telegram.payload) != 2:
            raise(CouldNotParseShutterTelegram)

        # telegram.payload[0] is 0x40 if state was requested, 0x80 if state of shutter was changed

        self.travelcalculator.set_position( telegram.payload[1] )
        self.after_update_callback(self)

    def current_position(self):
        return self.travelcalculator.current_position()

    def is_travelling(self):
        return self.travelcalculator.is_travelling()

    def position_reached(self):
        return self.travelcalculator.position_reached()

    def is_open(self):
        return self.travelcalculator.is_open()

    def is_closed(self):
        return self.travelcalculator.is_closed()
