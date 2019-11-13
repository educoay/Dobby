#!/usr/bin/python

# ---------- Change log ----------
# See change log

# Email
import smtplib

# MQTT
import paho.mqtt.client as MQTT

# MISC
import datetime
import sys
import time
import random
import os
import json
import subprocess
import optparse
import argparse

# FTP
import ftplib
from StringIO import StringIO
# For unique file id
import uuid
import io

# For udp config
import socket

# MySQL
import MySQLdb

# Threding
import threading

# EP Logger
import pymodbus.client.sync as pyModbus

# For Push Notifications
import requests

# Used to calc uptime
Start_Time = datetime.datetime.now()

# System variables
Version = 102008
# First didget = Software type 1-Production 2-Beta 3-Alpha
# Secound and third didget = Major version number
# Fourth to sixth = Minor version number

# Execution options
# Instantiate the parser
parser = argparse.ArgumentParser(description='Serving the master')

parser.add_argument('--verbose', action='store_true',
                    help='Prints ALL Log output to terminal')
         
parser.add_argument("--version", help="prints the script version and quits",
                    action="store_true")

# Parse arguemnts
Dobby_Arugments = vars(parser.parse_args())

# Save or act on arugments
# Parse arguemnts
Dobby_Arugments = vars(parser.parse_args())

# Save or act on arugments
# Verbose
if Dobby_Arugments.get('verbose', False) is True: 
    Verbose = True
else:
    Verbose = False
# Version
if Dobby_Arugments.get('version', False) is True:
    print "Dobby script version: " + str(Version)
    quit()

# MySQL
MQTT_Topic_Dict = {}

# Used to store config from db
Dobby_Config = {}

# MQTT
MQTT_Client = MQTT.Client(client_id="Dobby", clean_session=True)

MQTT_Client_gBridge = ""

# ---------------------------------------- MISC ----------------------------------------
def Open_db(db="", Create_If_Missing=False):
    db_Name = db
    try:
        db = MySQLdb.connect(host="localhost",    # your host, usually localhost
                             user="dobby",         # your username
                             passwd="HereToServe",  # your password
                             db=db)        # name of the data base
        return db

    except (MySQLdb.Error, MySQLdb.Warning) as e:
        # Create db if requested
        if Create_If_Missing == True and int(e[0]) == 1049:
            Log("Debug", 'System', 'db', "Create db on missing True. Creating db: " + db_Name)
            # Create connection to MySQL without selecting a db
            db_Connection = Open_db()
            if db_Connection is not None:
                db_Curser = db_Connection.cursor()
                # Create db
                if Create_db(db_Curser, db_Name) == True:
                    Log("Debug", 'System', 'db', "Created db: " + db_Name)
                    return Open_db(db_Name)
                else:
                    Log("Debug", 'System', 'db', "Unable to connect to db: " + db_Name + " after creating it")
                    return None

            else:
                Log("Error", 'System', 'db', "Unable to create db: " + db_Name)
                return None
        else:
            Log("Error", 'System', 'db', "While opening db connection: " + str(e))
            return None


def Close_db(conn, cur):
    try:
        conn.commit()
        # Check if curser was created
        if cur is not None:
            cur.close()
        conn.close()
        return True

    except (MySQLdb.Error, MySQLdb.Warning) as e:
        Log("Error", 'System', 'db', "While closing curser: " + str(e))
        return False


def Create_db(db_Curser, db_Name):
    try:
        db_Curser.execute("CREATE DATABASE " + db_Name)
    except (MySQLdb.Error, MySQLdb.Warning) as e:
        # Error 1007 = db already exists
        if e[0] == 1007:
            Log("Debug", 'System', 'db', "While creating db: " + str(db_Name) + " db already exists")
            return True
        else:
            Log("Error", 'System', 'db', "While creating db: " + str(db_Name) + " - " + str(e))
            return False
    return True


def Get_System_Config_Value(db_Curser, Target, Header, Name, QuitOnError=True, Error_Value=""):
    try:
        db_Curser.execute("SELECT Value FROM `Dobby`.`SystemConfig` WHERE Target='" + Target + "' AND Header='" + Header + "' AND Name='" + Name + "'")
        data = db_Curser.fetchone()
    except (MySQLdb.Error, MySQLdb.Warning) as e:
        if QuitOnError is True:
            Log('Fatal', 'System', 'db', "Unable to get system setting: " + Target + "-" + Header + "-" + Name + " - Error: " + str(e) + " - This setting is required for the system to run. Quitting")
            quit()

    if data is None and Error_Value is not "":
        Log("Debug", "System", "Settings", "Unable to get system setting: " + str(Target) + "-" + str(Header) + "-" + str(Name) + " - Defaulting to error value: " + str(Error_Value))
        return Error_Value

    if data is None and QuitOnError is True:
        Log('Fatal', 'System', 'db', "Unable to get system setting: " + Target + "-" + Header + "-" + Name + " this setting is required for the system to run. Quitting")
        quit()

    return data[0]


def Table_Size_Check(db_Curser, Table, Max_Size):
    db_Curser.execute('SELECT count(*) FROM `' + Table + '`')
    
    Rows_Number_Of = db_Curser.fetchone()
    Rows_Number_Of = int(Rows_Number_Of[0])

    if Rows_Number_Of > Max_Size:
        # Its not possible to delete with offset so the best way i found is to get the last id we want to keep and delete everything before it
        # Get last log entry id, so we can delete everything before it
        db_Curser.execute("SELECT id FROM `" + Table + "` ORDER BY id DESC LIMIT 1 OFFSET " + str(Max_Size))
        # Calc how many rows we need to delete        
        Rows_To_Delete = Rows_Number_Of - Max_Size
        # Then delete all entries before it 
        db_Curser.execute("DELETE FROM `" + Table + "` WHERE id<=" + str(Rows_To_Delete) + ";")
        Log("Debug", "Dobby", "db", "Size check, deleting " + str(Rows_To_Delete) + " rows for table: " + Max_Size)


# ---------------------------------------- Logging ----------------------------------------
def Log(Log_Level, Log_Source, Log_Header, Log_Text):
    Log_Thread = threading.Thread(name='DobbyLogging', target=Write_Log, kwargs={"Log_Level": Log_Level, "Log_Source": Log_Source, "Log_Header": Log_Header, "Log_Text": Log_Text})
    Log_Thread.daemon = True
    Log_Thread.start()


def Write_Log(Log_Level, Log_Source, Log_Header, Log_Text):

    # Dobby_Config['Init'] is set true after the system is able to write to the db untill then print all messages
    if Dobby_Config.get('Init', False) is False:
        print "*" + Log_Level + " - " + Log_Source + " - " + Log_Header + " - " + Log_Text
        return

    # if Verbose is active print log message regarding log level
    if Verbose is True:
        print Log_Level + " - " + Log_Source + " - " + Log_Header + " - " + Log_Text

    if Log_Level_Check(Log_Source, Log_Level) is False:
        return

    # Strip unvanted caractors from the Log Text, if the chars belos is in the log text it will create a db error
    Log_Text = Log_Text.replace('"', "")

    db_Log_Connection = Open_db(Dobby_Config['Log_db'], Create_If_Missing=True)
    db_Log_Curser = db_Log_Connection.cursor()
    db_Log_Curser.execute("set autocommit = 1")

    SQL_String = 'INSERT INTO `' + Dobby_Config['Log_db'] + '`.`SystemLog` (LogLevel, Source, Header, Text) VALUES("' + Log_Level + '", "' + Log_Source + '", "' + Log_Header + '", "' + Log_Text + '");'

    try:
        db_Log_Curser.execute(SQL_String)
    except (MySQLdb.Error, MySQLdb.Warning) as e:
        # 1146 = Table is missing
        if e[0] == 1146:
            try:
                db_Log_Curser.execute("CREATE TABLE `" + Dobby_Config['Log_db'] + "`.`SystemLog` (`id` int(11) NOT NULL AUTO_INCREMENT, `DateTime` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP, `LogLevel` varchar(10) NOT NULL, `Source` varchar(75) NOT NULL, `Header` varchar(75) NOT NULL, `Text` varchar(250) NOT NULL, PRIMARY KEY (`id`))")
            except (MySQLdb.Error, MySQLdb.Warning) as e:
                # Error 1050 = Table already exists
                if e[0] != 1050:
                    # That the table already exists is not really an error could have been created by another log instance in the meantime
                    # Try to write log again
                    db_Log_Curser.execute(SQL_String)
        else:
            Log('Error', 'Logging', 'db', 'Error while logging: ' + str(e))

    if db_Log_Curser is not None:
        Table_Size_Check(db_Log_Curser, 'SystemLog', Dobby_Config['Log_Length_System'])

    Close_db(db_Log_Connection, db_Log_Curser)


def Log_Level_Check(Log_Source, Log_Level):

    Log_Level = Log_Level.lower()
    Check_Level = Dobby_Config['Log_Level_System']

    Known_Levels_Dict = {'KeepAliveMonitor': Dobby_Config['Log_Level_KeepAliveMonitor'], 'MQTTConfig': Dobby_Config['Log_Level_MQTT_Config'], 'MQTT Functions': Dobby_Config['Log_Level_MQTT_Functions'], 'MQTT': Dobby_Config['Log_Level_MQTT'], 'Log Trigger': Dobby_Config['Log_Level_Log_Trigger'], 'Mail Trigger': Dobby_Config['Log_Level_Mail_Trigger'], 'Spammer': Dobby_Config['Log_Level_Spammer'], 'APC Monitor': Dobby_Config['Log_Level_APC_Monitor']}

    for Key, Variable in Known_Levels_Dict.iteritems():
        if Log_Source == Key and Variable != "":
            Check_Level = Variable

    if Log_Level in ["debug", "info", "warning", "error", "critical", "fatal"]:
        if Check_Level == "debug":
            return True

    if Log_Level in ["info", "warning", "error", "critical", "fatal"]:
        if Check_Level == "info":
            return True

    if Log_Level in ["warning", "error", "critical", "fatal"]:
        if Check_Level == "warning":
            return True

    if Log_Level in ["error", "critical", "fatal"]:
        if Check_Level == "error":
            return True

    if Log_Level in ["critical", "fatal"]:
        if Check_Level == "critical":
            return True

    if Log_Level in ["fatal"]:
        if Check_Level == "fatal":
            return True

    return False


# ---------------------------------------- Counters ----------------------------------------
class Counters:
    # How often does esch spammer read write to the db (sec)
    db_Refresh_Rate = 30
    Loop_Delay = 0.500

    def __init__(self):
        # Log event
        Log("Info", "Counters", "Checker", "Initializing")

        self.Agent_Dict = {}

        # Start checker thread
        File_Change_Checker_Thread = threading.Thread(target=self.Checker, kwargs={}, name="DobbyCounterChecker")
        File_Change_Checker_Thread.daemon = True
        File_Change_Checker_Thread.start()

    def Checker(self):
        # Start eternal loop
        while True:
            db_Connection = Open_db("Dobby")
            db_Curser = db_Connection.cursor()

            db_Curser.execute("SELECT id, Name, Last_Modified FROM Dobby.Counters")
            Counters_db = db_Curser.fetchall()

            Close_db(db_Connection, db_Curser)

            for i in Counters_db:
                id = str(i[0])
                Name = str(i[1])
                Last_Modified = i[2]

                # Agent not in dict so add it
                if id not in self.Agent_Dict:
                    # Log event
                    Log("Debug", "Counters", "Checker", "Starting: " + id + " - " + Name)
                    # Creat Agent
                    self.Agent_Dict[id] = self.Agent(id)

                # Agent in dict so check if there was changes
                else:
                    # Change to Counters
                    if str(self.Agent_Dict[id].Last_Modified) != str(Last_Modified):
                        # Log event
                        Log("Debug", "Counters", "Checker", "Change found in: " + id + " - " + Name + " restarting agent")
                        # Kill agent
                        self.Agent_Dict[id].Kill()
                        # Create a new agent
                        self.Agent_Dict[id] = self.Agent(id)

                # Sleep random time to go easy on the db
                time.sleep(random.uniform(0.150, 0.500))

            time.sleep(Counters.db_Refresh_Rate)

    class Agent:
        def __init__(self, id):

            self.id = int(id)

            db_Connection = Open_db("Dobby")
            db_Curser = db_Connection.cursor()

            db_Curser.execute("SELECT Name, `Log Trigger id`, `json Tag`, `Refresh Rate`, Enabled, Ticks, Math, `Last Triggered`, `Last_Modified` FROM Dobby.Counters WHERE id='" + str(self.id) + "';")
            Counters_Info = db_Curser.fetchone()

            Close_db(db_Connection, db_Curser)

            self.Name = str(Counters_Info[0])

            # Can't log event before now if you want to use name
            Log("Debug", "Counters", self.Name, 'Initializing')

            self.Log_Trigger_id = Counters_Info[1]
            self.json_Tag = Counters_Info[2]
            self.Refresh_Rate = float(Counters_Info[3])
            # self.Enabled = bool(Counters_Info[4])
            self.Next_Check = Counters_Info[7] + datetime.timedelta(seconds=self.Refresh_Rate)
            self.Ticks = Counters_Info[5]
            self.Math_Formular = Counters_Info[6]
            # self.Last_Triggered = Counters_Info[7]
            self.Last_Modified = Counters_Info[8]

            # Check if Counter is Enabled
            if bool(Counters_Info[4]) == 0:
                Log("Debug", "Counters", self.Name, 'Disabled - Not starting agent')
                quit()

            self.Kill_Command = False

            Log("Debug", "Counters", self.Name, 'Initialization compleate')

            Agent_Thread = threading.Thread(target=self.Run, kwargs={}, name="DobbyCounterAgent" + str(self.id))
            Agent_Thread.daemon = True
            Agent_Thread.start()


        # ========================= Agent - Kill =========================
        def Kill(self):
            Log("Debug", "Counters", self.Name, "Kill command issue")
            self.Kill_Command = True


        # ========================= Agent - Kill Now =========================
        def Kill_Now(self):
            Log("Debug", "Counters", self.Name, "Killing, buy buy")
            quit()


        # ========================= Agent - Run =========================
        def Run(self):
            # Log event
            Log("Info", "Counters", self.Name, "Running")
            # Start eternal loop
            while True:

                # Check if its time to check
                if self.Next_Check < datetime.datetime.now():
                
                    Log("Debug", "Counters", self.Name, "Checking")

                    # Calculate new value
                    ## Open db connection
                    db_Connection = Open_db("Dobby")
                    db_Curser = db_Connection.cursor()

                    # Agent Info
                    ## self.Name
                    ## self.id
                    ## self.Log_Trigger_id
                    ## self.json_Tag
                    ## self.Refresh_Rate
                    ## self.Next_Check
                    ## self.Ticks
                    ## self.Math_Formular

                    # Get last reset id
                    try:
                        db_Curser.execute('SELECT id FROM DobbyLog.Log_Trigger_' + str(self.Log_Trigger_id) + ' where Value="Reset" and json_Tag="' + str(self.json_Tag) + '" order by id desc Limit 1;')
                        Last_Reset_ID = db_Curser.fetchone()
                    except (MySQLdb.Error, MySQLdb.Warning) as e:
                        Log("Error", "Counters", self.Name, "Unable to get agent info from db, killing agent. db error:" + str(e[0]) + ": " + str(e[1]))
                        # Kill the agent so we dont kill the db to reading agent info all the time
                        self.Kill()

                    # Check if db select above failed if so do nothing
                    if self.Kill_Command is not True:
                        
                        # Check if reset was in table if not set it Last_Reset_ID to 0
                        if Last_Reset_ID is None:
                            Last_Reset_ID = 0
                        else:
                            Last_Reset_ID = Last_Reset_ID[0]

                        # Get list of all "Boot" since last "Reset"
                        db_Curser.execute('SELECT id FROM DobbyLog.Log_Trigger_' + str(self.Log_Trigger_id) + ' where id > "' + str(Last_Reset_ID) + '" and Value="Boot" and json_Tag="' + str(self.json_Tag) + '" order by id desc;')
                        Boot_id_List = db_Curser.fetchall()

                        Counter_State = 0

                        # Check if any "Boot" since last "Reset"
                        if Boot_id_List == ():
                            # When no boot and reset present then just use last number entry
                            db_Curser.execute('SELECT Value FROM DobbyLog.Log_Trigger_' + str(self.Log_Trigger_id) + ' where id > "' + str(Last_Reset_ID) + '" and json_Tag="' + str(self.json_Tag) + '" order by id desc limit 1;')
                            Counter_State = db_Curser.fetchone()
                            if Counter_State is None:
                                Counter_State = 0
                            else:
                                Counter_State = int(Counter_State[0])

                        else:
                            # Add the last Value before first boot aka the current sensor value
                            db_Curser.execute('SELECT Value FROM DobbyLog.Log_Trigger_' + str(self.Log_Trigger_id) + ' where id > "' + str(Boot_id_List[0][0]) + '" and json_Tag="' + str(self.json_Tag) + '" order by id desc limit 1;')
                            Counter_State = db_Curser.fetchone()

                            # if None is returned then "Boot" was the last value hence we will set Counter_State to 0
                            if Counter_State is None:
                                Counter_State = 0
                            else:
                                # Remove tubler
                                Counter_State = int(Counter_State[0])

                            # Add each value just before "Boot"
                            for Boot_id in Boot_id_List:

                                # When selecting based on "Boot" remember to do less then Boot_id to get the value just before
                                db_Curser.execute('SELECT Value FROM DobbyLog.Log_Trigger_' + str(self.Log_Trigger_id) + ' where id > "' + str(Boot_id[0]) + '" and Value!="Boot" and Value!="Reset" and json_Tag="' + str(self.json_Tag) + '" order by id desc limit 1;')

                                db_Value = db_Curser.fetchone()

                                # Correct for instances where the device booted but posted no value
                                if db_Value is None:
                                    db_Value = 0
                                else:
                                    db_Value = db_Value[0]
                                # Add found value to Counter_State
                                Counter_State = Counter_State + int(db_Value)

                        # Check if value has changed and needs to be published
                        if int(Counter_State) != int(self.Ticks):

                            # Change self.Ticks
                            self.Ticks = Counter_State
                            # Do math
                            # Set string
                            Math_Value = self.Math_Formular
                            # Replace value
                            Math_Value = Math_Value.replace("[Value]", str(Counter_State))
                            # Do math
                            Math_Value = eval(Math_Value)
                            # Round value
                            Math_Value = round(Math_Value,2)

                            # Write values to db
                            db_Curser.execute("UPDATE `Dobby`.`Counters` SET `Ticks` = '" + str(Counter_State) + "' WHERE (`id` = '" + str(self.id) + "');")
                            db_Curser.execute("UPDATE `Dobby`.`Counters` SET `Calculated Value` = '" + str(Math_Value) + "' WHERE (`id` = '" + str(self.id) + "');")
                            db_Curser.execute("UPDATE `Dobby`.`Counters` SET `Last Triggered` = '" + str(datetime.datetime.now()) + "' WHERE (`id` = '" + str(self.id) + "');")

                            # Publish Values
                            MQTT_Client.publish(Dobby_Config['System_Header'] + '/Counters/Dobby/' + self.Name + "/Ticks", payload=Counter_State, qos=0, retain=True)
                            MQTT_Client.publish(Dobby_Config['System_Header'] + '/Counters/Dobby/' + self.Name, payload=Math_Value, qos=0, retain=True)

                    
                    # Save next check time            
                    self.Next_Check = datetime.datetime.now() + datetime.timedelta(seconds=self.Refresh_Rate)
                    
                    # Close db connection
                    Close_db(db_Connection, db_Curser)

                # Nite nite
                while self.Next_Check > datetime.datetime.now():
                    # Check if we need to kill our selvels
                    if self.Kill_Command is True:
                        self.Kill_Now()
                    # Sleep for a bit
                    time.sleep(Counters.Loop_Delay)



                    # # Get values since last reset
                    # db_Curser.execute('SELECT Value FROM DobbyLog.Log_Trigger_' + str(self.Log_Trigger_id) + ' where id > "' + str(Last_Reset_ID) + '" and json_Tag="' + str(self.json_Tag) + '" order by id desc;')
                    # db_Data = db_Curser.fetchall()

                    # print "Agent: " + self.Name

                    # elif "Boot" in db_Data:
                    #     print "BOOT IT IS"


                    # # if boot is not in the list just use the last number in the db
                    # else:
                    #     print "ELSES fisse: " + str(db_Data[0][0])
                        # # Check if the select command returned anything, if not there is no entries in the db
                        # if db_Data == ():
                        #     print "db_Data == ()"
                        #     Counter_State = 0
                        



                    # # if db data is empyth set counter to 0
                    # if db_Data != ():
                    #     # Get the value before each boot message and add them together to the first value
                    #     try:
                    #         if db_Data[0][0] != "Boot":
                    #             Counter_State = int(db_Data[0][0])
                    #     except IndexError:
                    #         # Set Counter_State to 0 if not 
                    #         pass

                    #     Add_Next = False

                    #     for Entry in db_Data:
                    #         print "Entry: " + str(Entry)

                    #     for i in range(len(db_Data)):
                    #         # If Value == "Boot" add next value if not
                    #         if db_Data[i][0] == 'Boot':
                    #             Add_Next = True
                            
                    #         elif Add_Next == True:
                    #             Counter_State = Counter_State + int(db_Data[i][0])
                    #             Add_Next = False





# ---------------------------------------- MQTT Commands ----------------------------------------
def MQTT_Commands(Topic, Payload):
    Topic = Topic.replace(Dobby_Config['System_Header'] + "/Commands/Dobby/", "")

    Log("Debug", "MQTT Commands", "Request", Topic + " - " + Payload)

    if "Config" in Topic:
        Device_Config(Payload)
        return

    # Rewrite for supervistor
    elif "Power" in Topic:
        # Power_Thread = threading.Thread(target=Power, kwargs={"Payload": Payload})
        # Power_Thread.daemon = True
        # Power_Thread.start()
        return

    # elif "KeepAliveMonitor" in Topic:
    #     MQTT_Commands_KeepAliveMontor(Topic, Payload)
    #     return

    elif Topic in "Test":
        Log("Test", "MQTTCommands", "Executing", Topic + " - " + Payload)
        return

    # elif Topic in "MQTTSQL":
    #     MQTT_SQL(Payload)
    #     return

    Log("Warning", "MQTTCommands", "Request", Topic + " - " + Payload + " - Not found")


# ---------------------------------------- Device Config ----------------------------------------
def Device_Config(Payload):
    if ";" in Payload:
        Payload = Payload.replace(";", "")

    Payload = Payload.split(",")
    # 0 Device name
    # 1 Config id
    # 2 Request type

    # Check if all config request info has been provided
    Config_id = 0
    # If not log Warning and return
    try:
        Device_Name = str(Payload[0])
    except (ValueError, IndexError):
        Log("Warning", "Device Config", "Request", "Missing 'Device Name' from request")
        return
    try:
        Config_id = str(Payload[1])
    except (ValueError, IndexError):
        Log("Warning", "Device Config", "Request", "Missing 'Config id' from request")
        return
    # Get reqyest type
    try:
        Request_Type = Payload[2]
    except (ValueError, IndexError):
        Log("Warning", "Device Config", "Request", "Missing 'Request type' from request")
        # Set Request_Type to MQTT if none specified to backword compatibility
        Request_Type = 'MQTT'
        return
    # IP is only required for: FTP and UDP
    if Request_Type in ('FTP', 'UDP'):
        try:
            Device_IP = Payload[3]
        except (ValueError, IndexError):
            Log("Warning", "Device Config", "Request", "Missing 'Request type' from request")
            return

    Log("Info", "Device Config", "Request", Device_Name)
    
    db_Connection = Open_db("Dobby")
    db_Curser = db_Connection.cursor()

    # Get device's "config id" from db
    try:
        db_Curser.execute("SELECT Config_ID FROM Dobby.DeviceConfig WHERE Hostname='" + Device_Name + "';")
        Device_db_Config_id = db_Curser.fetchone()

    except (MySQLdb.Error, MySQLdb.Warning) as e:
        if e[0] == 1146:
            Log("Warning", "Device Config", "Missing", Device_Name)
        else:
            Log("Error", "Device Config", "db error", str(e[0]))
        Close_db(db_Connection, db_Curser)
        return

    # Config if config is in db
    if Device_db_Config_id is None:
        Log("Warning", "Device Config", "Missing", Device_Name)
        return
    else:
        # Remove tubler
        Device_db_Config_id = Device_db_Config_id[0]

    # Check config id agents current config id and return if =
    if Device_db_Config_id == int(Config_id):
        Log("Debug", "Device Config", "Config up to date", Device_Name + " id: " + Config_id)
        return
        # if UDP_Request is True:
        #     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        #     sock.sendto("OK".encode('utf-8'), (Device_IP, 8888))
        #     sock.close()
        #     return
        # else:

    # Log event
    Log("Debug", "Device Config", "Config outdated", Device_Name + " Device Config ID: " + Config_id + " Config ID: " + str(Device_db_Config_id))


    # Config outdated, getting device config
    try:
        # Get config name
        db_Curser.execute("SELECT DISTINCT `COLUMN_NAME` FROM `INFORMATION_SCHEMA`.`COLUMNS` WHERE `TABLE_SCHEMA`='Dobby' AND `TABLE_NAME`='DeviceConfig';")
        Config_Name_List = db_Curser.fetchall()
        # Get config value
        db_Curser.execute("SELECT * FROM DeviceConfig WHERE Hostname='" + Device_Name + "';")
        Config_Value_List = db_Curser.fetchall()

    except (MySQLdb.Error, MySQLdb.Warning) as e:
        if e[0] == 1146:
            Log("Warning", "Device Config", "Missing", Device_Name)
        else:
            Log("Error", "Device Config", "db error", str(e[0]))
        Close_db(db_Connection, db_Curser)
        return

    Close_db(db_Connection, db_Curser)

    if Config_Name_List is () or Config_Value_List is ():
        Log("Error", "Device Config", "Config Empthy", Device_Name)
        return

    # Create json config
    Config_Dict = {}
    Interation = 0
    Ignore_List = ('id', 'Config_Active', 'Last_Modified')
    Empthy_Values = ('None', '')

    for Config_Name in Config_Name_List:
        # Correct name for human readable
        Config_Name = str(Config_Name[0])
        Config_Value = str(Config_Value_List[0][Interation])

        Add_Value = False

        # Check if config entry needs to be ignored
        if Config_Name not in Ignore_List:
            # Ignore all empyth values
            if Config_Value in Empthy_Values:
                # Dont ignore "System sub header"
                if Config_Name == "System_Sub_Header":
                    Add_Value = True
            # Value not empyth
            else:
                Add_Value = True

        if Add_Value is True:
            # Add config to config dict
            Config_Dict[Config_Name] = Config_Value
        
        Interation = Interation + 1


    # Check request type
    # MQTT Request
    if Request_Type == "MQTT":
        Log("Info", "Device Config", "MQTT", 'Publish config to: - ' + Device_Name)
        # Publish json
        MQTT_Client.publish(Dobby_Config['System_Header'] + "/Commands/" + Device_Name + "/Config", payload=json.dumps(Config_Dict) + ";", qos=0, retain=False)


    # UDP Request
    elif Request_Type == "UPD":
        Log("Info", "Device Config", "UDP", 'Send to: - ' + Device_Name + " - IP: " + Device_IP)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(json.dumps(Config_Dict).encode('utf-8'), (Device_IP, 8888))
        sock.close()


    # FTP Request
    elif Request_Type == "FTP":
        Log("Info", "Device Config", "FTP", 'Upload to: - ' + Device_Name + " - IP: " + Device_IP)

        # Generate unique config id
        Config_File_Name = "/var/tmp/Dobby/" + str(Device_Name)

        # Check if temp dir exists
        if not os.path.exists("/var/tmp/Dobby/"):
            os.makedirs("/var/tmp/Dobby/")

        # Write json to file
        # NOTE - Cant get "with open" to work for some odd reason
        Config_File = open("%s.json" % Config_File_Name, "w")
        json.dump(Config_Dict, Config_File)
        Config_File.flush
        Config_File.close

        # Upload file
        # FIX - Change user and pass
        try:
            FTP_Connection = ftplib.FTP(Device_IP,'dobby','heretoserve')
        except socket.error as Error:
            Log("Info", "Device Config", "FTP", 'Upload to: - ' + Device_Name + " - IP: " + Device_IP + " Failed: " + str(Error))
            # close file and FTP
            return

        # Open and read file to send
        with open(Config_File_Name + ".json", 'r') as Config_File:
            FTP_Connection.storbinary('STOR Dobby.json', open(Config_File_Name + ".json", 'rb'))

        # close file and FTP
        FTP_Connection.quit()

        # Not deleting file so the last generated config is saved, uncomment below to delete file
        # os.remove(Config_File_Name)

        # 10 sec delay so the device can reconnect after ftp upload
        time.sleep(10)

        # Send reboot command to device
        MQTT_Client.publish(Dobby_Config['System_Header'] + "/Commands/" + Device_Name + "/Power", payload="Reboot;", qos=0, retain=False)


# ---------------------------------------- MISC ----------------------------------------
def Is_json(myjson):
    # A single entry is not consider a json sitring
    if "{" not in myjson:
        return False

    try:
        myjson = json.loads(myjson)
    except ValueError, e:
        myjson = e
        return False

    return True






# ---------------------------------------- Log Trigger ----------------------------------------
class Log_Trigger():
    
    # How often the db is cheched for changes
    Refresh_Rate = 5

    def __init__(self):
        # Log event
        Log("Info", "Log Trigger", "System", "Initializing")

        db_Connection = Open_db("Dobby")
        db_Curser = db_Connection.cursor()

        db_Curser.execute("SELECT id, Name, Tags, Max_Entries, Topic FROM Dobby.Log_Trigger WHERE Enabled='1'")
        Log_Trigger_db = db_Curser.fetchall()

        for i in range(len(Log_Trigger_db)):
            # id =            0
            # Name =          1
            # Tags =          2
            # Max_Entries =   3
            # Topic =         4

            # Log Event
            Log("Debug", "Log Trigger", Log_Trigger_db[i][1], "Subscribing to: '" + Log_Trigger_db[i][4] + "'")
            # Add topic to topic tict
            MQTT_Add_Sub_Topic(str(Log_Trigger_db[i][4]), 'Log Trigger', {'id': Log_Trigger_db[i][0], 'Name': Log_Trigger_db[i][1], 'Tags': Log_Trigger_db[i][2], 'Max_Entries': Log_Trigger_db[i][3]})
            # Subscribe
            MQTT_Client.subscribe(str(Log_Trigger_db[i][4]))
            # Register callbacks
            MQTT_Client.message_callback_add(str(Log_Trigger_db[i][4]), MQTT_On_Message_Callback)

        Close_db(db_Connection, db_Curser)

    @classmethod
    def On_Message(cls, Trigger_Info, Payload, Retained):

        # Log only none retained messages
        if Retained is 0:
            # json value
            if Is_json(Payload) is True:
                # Create json
                root = json.loads(Payload)
                # Split headers into seperate topics
                for json_Log_Source, json_Log_Value in root.items():
                    Log_Trigger.Write_Value_To_db(Trigger_Info, json_Log_Value, json_Tag=json_Log_Source)
                    # None json value
            else:
                Log_Trigger.Write_Value_To_db(Trigger_Info, Payload)


    @classmethod
    def Write_Value_To_db(cls, Trigger_Info, Value, json_Tag=''):

        Log("Debug", "Log Trigger", "Logging", "Value: " + str(Value) + " json_Tag: " + str(json_Tag))

        db_Connection = Open_db()
        db_Curser = db_Connection.cursor()

        db_Curser.execute("set autocommit = 1")

        # Make sure Log_Value is string
        Value = str(Value)
        # Remove the ";" at the end if there
        if Value[-1:] == ";":
            Value = Value[:-1]

        SQL_Table_Name = Dobby_Config['Log_db'] + "`.`Log_Trigger_"  + str(Trigger_Info['id'])
        SQL_String = "INSERT INTO `" + SQL_Table_Name + "` (json_Tag, Value) Values('" + str(json_Tag) + "' , '" + Value + "');"
        
        # Log Value
        try:
            db_Curser.execute(SQL_String)
        except (MySQLdb.Error, MySQLdb.Warning) as e:
            # Table missing, create it
            if e[0] == 1146:
                Log("Info", "Log Trigger", "db table missing", "Creating: " + SQL_Table_Name)
                try:
                    # To create table
                    db_Curser.execute("CREATE TABLE `" + SQL_Table_Name + "` (`id` int(11) NOT NULL AUTO_INCREMENT, `json_Tag` varchar(75) NOT NULL, `Value` varchar(75) NOT NULL, `DateTime` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (`id`))ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4;")
                    # Try logging the message again
                    db_Curser.execute(SQL_String)

                except (MySQLdb.Error, MySQLdb.Warning) as e:
                    # Error 1050 = Table already exists
                    if e[0] != 1050:
                        Log("Fatal", "Log Trigger", Trigger_Info['Name'], "Unable to create log db table, failed with error: " + str(e))
                        return
            else:
                Log("Critical", "Log Trigger", "db", "Unable to log message. Error: " + str(e))
                return

        # Delete rows > max
        db_Curser.execute("SELECT count(*) FROM `" + SQL_Table_Name + "`;")
        Rows_Number_Of = db_Curser.fetchone()

        if Rows_Number_Of[0] > int(Trigger_Info['Max_Entries']):
            Rows_To_Delete = Rows_Number_Of[0] - int(Trigger_Info['Max_Entries'])
            
            db_Curser.execute("DELETE FROM `" + SQL_Table_Name + "` ORDER BY 'id' LIMIT " + str(Rows_To_Delete) + ";")
            
            Log("Debug", "Dobby", Trigger_Info['Name'], "History Length reached, deleting " + str(Rows_To_Delete))

        # Change Last_Trigger
        db_Curser.execute("UPDATE `Dobby`.`Log_Trigger` SET `Last_Trigger`='" + str(datetime.datetime.now()) + "' WHERE `id`='" + str(Trigger_Info['id']) + "';")

        # Log event
        Log("Debug", "Log Trigger", Trigger_Info['Name'], "Valure capured: " + Value)

        Close_db(db_Connection, db_Curser)
















# ---------------------------------------- Action Trigger ----------------------------------------
class Action_Trigger():
    # How often the db is cheched for changes
    Refresh_Rate = 5
    # Create needed variables
    Active_Triggers = {}
    # Trigger_Timeouts = {}
    # MQTT_Target_Checks = {}
    Retrigger_Counter = {}

    def __init__(self):
        # Log event
        Log("Info", "Action Trigger", "Checker", "Initializing")

        # Start checker thread
        File_Change_Checker_Thread = threading.Thread(name='DobbyActionTriggerChecker', target=self.Checker, kwargs={})
        File_Change_Checker_Thread.daemon = True
        File_Change_Checker_Thread.start()

    def Checker(self):
        # Start eternal loop
        while True:
            # Open db connection get id, Last Modified
            db_Connection = Open_db("Dobby")
            db_Curser = db_Connection.cursor()

            # Get id and Last Modified to check if Action Triggers needs to be started
            db_Curser.execute("SELECT id, Last_Modified FROM Dobby.`Action_Trigger` WHERE Enabled=1;")
            Action_Info = db_Curser.fetchall()

            # Close db connection
            Close_db(db_Connection, db_Curser)

            for i in range(len(Action_Info)):
                # Action_Info[i][0] - id
                # Action_Info[i][1] - Last Modified

                # Check if the trigger is in the Active_Triggers dict
                if Action_Info[i][0] in self.Active_Triggers:
                    
                    # Check if last modified changed
                    if self.Active_Triggers[Action_Info[i][0]] != Action_Info[i][1]:
                        self.Active_Triggers[Action_Info[i][0]] = Action_Info[i][1]
                        self.Restart_Trigger(Action_Info[i][0])
                        
                # If not add then to the list and start the trigger
                else:
                    self.Active_Triggers[Action_Info[i][0]] = Action_Info[i][1]
                    # Start the trigger
                    self.Start_Trigger(Action_Info[i][0])

            # Sleep till next check
            time.sleep(self.Refresh_Rate)
    

    def Start_Trigger(self, id):

        Trigger_Info = self.Get_Trigger_Info(id)

        # Log Event
        Log("Debug", "Action Trigger", str(Trigger_Info[0]), "Starting")
        Log("Debug", "Action Trigger", str(Trigger_Info[0]), "Subscribing to: '" + str(Trigger_Info[1]) + "'")
        # Add topic to topic tict
        MQTT_Add_Sub_Topic(str(Trigger_Info[1]), 'Action Trigger', id)
        # Subscribe
        MQTT_Client.subscribe(str(Trigger_Info[1]))
        # Register callbacks
        MQTT_Client.message_callback_add(str(Trigger_Info[1]), MQTT_On_Message_Callback)
        # Create or reset retrigger
        Action_Trigger.Retrigger_Counter[id] = 0

        # # Create Timeout Trigger
        # self.Trigger_Timeouts[id] = Timeout_Trigger()
        # print "CREATE target trigger here if timeout_set is set"



    def Stop_Trigger(self, id):

        Trigger_Info = self.Get_Trigger_Info(id)

         # Log Event
        Log("Debug", "Action Trigger", str(Trigger_Info[0]), "Stopping")
        Log("Debug", "Action Trigger", str(Trigger_Info[0]), "Unsubscribing from: '" + str(Trigger_Info[1]) + "'")

        MQTT_Del_Sub_Topic(Trigger_Info[1], 'Action Trigger', id)


    def Restart_Trigger(self, id):
        self.Start_Trigger(id)
        self.Stop_Trigger(id)


    def Get_Trigger_Info(self, id):
        # Open db connection
        db_Connection = Open_db("Dobby")
        db_Curser = db_Connection.cursor()

        db_Curser.execute("SELECT Name, `MQTT Target` FROM Dobby.`Action_Trigger` WHERE id="+ str(id) + ";")
        Trigger_Info = db_Curser.fetchone()
        # Trigger_Info[0] - Name
        # Trigger_Info[1] - Target

        # Close db connection
        Close_db(db_Connection, db_Curser)

        # Return info
        return Trigger_Info

    @classmethod
    def On_Message(cls, id, Topic, Payload):

        db_Connection = Open_db("Dobby")
        db_Curser = db_Connection.cursor()

        db_Curser.execute("set autocommit = 1")

        db_Curser.execute("SELECT Name, `Alert State`, `MQTT Payload Clear`, `MQTT Payload Trigger`, `Alert Target`, `Alert Payload Clear`, `Alert Payload Trigger`, Timeout, `Timeout Alert Target` FROM Dobby.Action_Trigger WHERE id=" + str(id) + ";")
        Trigger_Info = db_Curser.fetchone()

        Name = Trigger_Info[0]
        Alert_State = Trigger_Info[1]
        MQTT_Payload_Clear = Trigger_Info[2]
        MQTT_Payload_Trigger = Trigger_Info[3]
        Alert_Target = Trigger_Info[4]
        Alert_Payload_Clear = Trigger_Info[5]
        Alert_Payload_Trigger = Trigger_Info[6]
        Timeout_Sec =  Trigger_Info[7]
        Timeout_Alert_Target =  Trigger_Info[8]


        # Find out what to do
        Action = 2
        # 0 = Clear
        # 1 = Trigger
        # 2 = In-between

        Trigger_Change = False

        if float(MQTT_Payload_Clear) == float(MQTT_Payload_Trigger):
            Log("Error", "Action Trigger", str(Name), 'Clear and Trigger payload is the same value')
            Close_db(db_Connection, db_Curser)
            return

        # High / Low Check
        # Value moving from Low to High
        elif (float(MQTT_Payload_Clear) <= float(MQTT_Payload_Trigger)) is True:
            # Clear check
            if float(MQTT_Payload_Clear) >= float(Payload):
                Action = 0

            # Trigger check
            elif float(MQTT_Payload_Trigger) <= float(Payload):
                Action = 1

        # Value moving from High to Low
        else:
            # Clear check
            if float(MQTT_Payload_Clear) <= float(Payload):
                Action = 0

            # Trigger check
            elif float(MQTT_Payload_Trigger) >= float(Payload):
                Action = 1

        # Clear
        if Action == 0:
            # Check agains current alert state
            if Action == Alert_State:
                # Check if its time to retrigger
                if Action_Trigger.Retrigger_Counter[id] > 3:
                    Log("Debug", "Action Trigger", str(Name), 'Retrigger Clear')
                    # Republish mqtt trigger message
                    MQTT_Client.publish(Alert_Target, payload=str(Alert_Payload_Clear) + ";", qos=0, retain=False)
                    # Reset retrigger counter
                    Action_Trigger.Retrigger_Counter[id] = 0
                else:
                    Log("Debug", "Action Trigger", str(Name), 'Already cleared ignoreing new clear value: ' + str(Payload))
                    # Add one to retrigger counter
                    Action_Trigger.Retrigger_Counter[id] = Action_Trigger.Retrigger_Counter[id] + 1
            else:
                Trigger_Change = True
                # Publish Message
                MQTT_Client.publish(Alert_Target, payload=str(Alert_Payload_Clear) + ";", qos=0, retain=False)
                Log("Info", "Action Trigger", str(Name), 'Cleared at: ' + str(Payload) + " Target: " + str(MQTT_Payload_Clear))
                # Reset retrigger counter
                Action_Trigger.Retrigger_Counter[id] = 0

        # Trigger
        elif Action == 1:
            # Check agains current alert state
            if Action == Alert_State:
                # Check if its time to retrigger
                if Action_Trigger.Retrigger_Counter[id] > 3:
                    Log("Debug", "Action Trigger", str(Name), 'Retrigger Trigger')
                    # Republish mqtt trigger message
                    MQTT_Client.publish(Alert_Target, payload=str(Alert_Payload_Trigger) + ";", qos=0, retain=False)
                    # Reset retrigger counter
                    Action_Trigger.Retrigger_Counter[id] = 0
                else:
                    Log("Debug", "Action Trigger", str(Name), 'Already triggered ignoreing new trigger value: ' + str(Payload))
                    # Add one to retrigger counter
                    Action_Trigger.Retrigger_Counter[id] = Action_Trigger.Retrigger_Counter[id] + 1
            else:
                Trigger_Change = True
                # Publish Message
                MQTT_Client.publish(Alert_Target, payload=str(Alert_Payload_Trigger) + ";", qos=0, retain=False)
                Log("Info", "Action Trigger", str(Name), 'Triggered at: ' + str(Payload) + " Target: " + str(MQTT_Payload_Trigger))
                # Reset retrigger counter
                Action_Trigger.Retrigger_Counter[id] = 0

        # In-between value
        elif Action == 2:
            Log("Debug", "Action Trigger", str(Name), 'In-between value received: ' + str(Payload))

        if Trigger_Change is True:
            # Change Alert_State
            db_Curser.execute("UPDATE `Dobby`.`Action_Trigger` SET `Alert State`='" + str(Action) + "' WHERE `id`='" + str(id) + "';")
            # Update Triggered_DateTime
            db_Curser.execute("UPDATE `Dobby`.`Action_Trigger` SET `Triggered DateTime`='" + str(datetime.datetime.now()) + "' WHERE `id`='" + str(id) + "';")
            # Reset retrigger counter
            Action_Trigger.Retrigger_Counter[id] = 0

        # Close the db connection
        Close_db(db_Connection, db_Curser)

        
        # if Timeout_Sec is not None:
        #     # Start trigger timeout
        #     Action_Trigger.Trigger_Timeouts[id].Reset(Timeout_Sec, Timeout_Alert_Target)
            
            # If timeout is set the Target will be checked for state as well
            # the check is done at 2/3 of timepout to assure reply from target can time out
            # Action_Trigger.MQTT_Target_Checks[id].Reset(Timeout_Sec, Topic)
            
            #     MQTT_Target_Check(Topic, Action)
            
            # print 'Timeout_Sec' 
            # print Timeout_Sec




# ---------------------------------------- Send Alert ----------------------------------------
def Send_Alert(id, Value=None, Subject=None, Text=None):

    # Get Alert into
    ## Open db connection
    db_Connection = Open_db("Dobby")
    db_Curser = db_Connection.cursor()

    db_Curser.execute("SELECT Name, `Mail Target`, `MQTT Target`, `Push Target` FROM Dobby.`Alert_Targets` WHERE id=" + str(id) + ";")
    Alert_Info = db_Curser.fetchone()

    ## Only get subject text if none is set
    if Subject is None:
        db_Curser.execute("SELECT Subject FROM Dobby.`Alert_Targets` WHERE id=" + str(id) + ";")
        Subject = db_Curser.fetchone()
        Subject = Subject[0]
    if Text is None:
        db_Curser.execute("SELECT Text FROM Dobby.`Alert_Targets` WHERE id=" + str(id) + ";")
        Text = db_Curser.fetchone()
        Text = Text[0]

    ## Close db connection
    Close_db(db_Connection, db_Curser)

    Alert_Name = Alert_Info[0]
    Mail_Target = Alert_Info[1]
    MQTT_Target = Alert_Info[2]
    Push_Target = Alert_Info[3]

    # Add value to Text if value is set
    if Value is not None and Value != "":
        Text = Text.replace('*value*', str(Value))


    # Mail Alerts
    if Mail_Target is not None and Mail_Target != "":
        Send_Mail(Mail_Target, Subject, Text)


    # MQTT Messages
    if MQTT_Target is not None and MQTT_Target != "":
        # Remove any spaces
        MQTT_Target = MQTT_Target.replace(" ", "")

        Target_List = []

        # Multiple targets
        if "," in MQTT_Target:
            Target_List = MQTT_Target.split(",")

        # Single target
        else:
            Target_List.append(MQTT_Target)

        # Publish MQTT Message 
        for Target_Topic in Target_List:
            # Publish message
            MQTT_Client.publish(Target_Topic, payload=Text, qos=0, retain=False)
            # Log event
            Log("Debug", "System", "MQTT", 'Publish - Topic: ' + str(Target_Topic) + " Payload: " + str(Text))
            

    if Push_Target is not None and Push_Target != "":
        Send_Push(Push_Target, Subject, Text)


# # ---------------------------------------- Timeout Trigger ----------------------------------------
# class Timeout_Trigger():

#     Check_Delay = 0.500
    
#     def __init__(self):
#         # Log event
#         Log("Debug", "System", "Timeout Trigger", "Initializing")

#         # Create vars
#         self.Timeout_At = datetime.datetime.now()
#         self.Alert_Target_id = ""
#         self.Delete_Me = False
#         self.Triggered = True

#         # Start timeout
#         Timer_Thread = threading.Thread(target=self.Run)
#         Timer_Thread.daemon = True
#         Timer_Thread.start()

#     def Reset(self, Timeout, Alert_Target_id):
#         # Log event
#         Log("Debug", "System", "Timeout Trigger", "Reset alert id: " + str(Alert_Target_id))
        
#         # Save vars
#         self.Alert_Target_id = Alert_Target_id
#         ## Add timeout to current time to get Timeout_At
#         self.Timeout_At = datetime.datetime.now() + datetime.timedelta(seconds=Timeout)
#         ## Alert id
#         self.Alert_Target_id = Alert_Target_id

#         # Reset triggered
#         self.Triggered = False
        

#     def Delete(self):
#         Log("Debug", "System", "Timeout Trigger", "Deleted alert id: " + str(self.Alert_Target_id))
#         # Mark thread for deletions
#         self.Delete_Me = True


#     def Trigger_Timeout(self):
#         if self.Triggered == True:
#             return
        
#         # Set var to prevent retrigger
#         self.Triggered = True

#         # Log event
#         Log("Debug", "System", "Timeout Trigger", "Triggered alert id:" + str(self.Alert_Target_id))
        
#         # Get alert information from db        
#         ## Open db connection
#         db_Connection = Open_db("Dobby")
#         db_Curser = db_Connection.cursor()
#         # Set autocommit so no delay on saving changes
#         db_Curser.execute("set autocommit = 1")

#         ## Get id and Last Modified to check if gBridge Triggers needs to be started
#         db_Curser.execute("SELECT `Mail Target`, `MQTT Target`, `Push Target`, Subject, Body FROM Dobby.`Alert_Targets` WHERE id=" + str(self.Alert_Target_id) + ";")
#         Alert_Info = db_Curser.fetchone()

#         # Change Last_Trigger
#         db_Curser.execute("UPDATE `Dobby`.`Alert_Targets` SET `Last_Trigger`='" + str(datetime.datetime.now()) + "' WHERE `id`='" + str(id) + "';")

#         ## Close db connection
#         Close_db(db_Connection, db_Curser)

#         # Send Alerts
#         ## 0 = Mail Target
#         ## 1 = MQTT Target
#         ## 2 = Push Target
#         ## 3 = Subject
#         ## 4 = Body
#         print "fix timout trigger"
#         # Send_Alert(Alert_Info[3], Alert_Info[4], None, Alert_Info[0], Alert_Info[1], Alert_Info[2])


#     def Run(self):
#         # Just sleep untill id is set
#         while self.Alert_Target_id == "" and self.Delete_Me == False:
#             # Sleep untill next check
#             time.sleep(self.Check_Delay)

#         # When id is set start the timeout
#         while self.Delete_Me == False:
 
#             # Check if current time vs timeout at time
#             if self.Timeout_At < datetime.datetime.now():
#                 self.Trigger_Timeout()

#             # Sleep untill next check
#             time.sleep(self.Check_Delay)


# ---------------------------------------- gBridge Trigger ----------------------------------------
# From local to gBridge
# def gBridge_Trigger_Local(id, Topic, Payload):
#     # Log event
#     Log("Debug", "gBridge Trigger", str(gBridge_Trigger.Active_Triggers[id]['Name']), "Dobby: " + str(Payload))
#     # Ignore "/set" messages to avoid message loops
#     if "/set" in Topic:
#         return
#     # Publish reply
#     MQTT_Client_gBridge.Publish_Reply(id, Topic, Payload)



# Form gBridge to local
class gBridge_Trigger():
    # How often the db is cheched for changes
    Refresh_Rate = 5

    Active_Triggers = {}

    # Create a MQTT client to connect to gBridge
    MQTT_Client = MQTT.Client(client_id="Dobby", clean_session=True)

    MQTT_Broker = ""
    MQTT_Base_Topic = ""

    Checker_Stop = False

    def __init__(self):
        # Log event
        Log("Info", "gBridge Trigger", "Checker", "Initializing")

        # Open db connection get id, Last Modified
        db_Connection = Open_db("Dobby")
        db_Curser = db_Connection.cursor()

        MQTT_User = Get_System_Config_Value(db_Curser, "gBridge_Trigger", "MQTT", "Username", False)
        MQTT_Pass = Get_System_Config_Value(db_Curser, "gBridge_Trigger", "MQTT", "Password", False)
        self.MQTT_Broker = Get_System_Config_Value(db_Curser, "gBridge_Trigger", "MQTT", "Broker", False)
        MQTT_Port = Get_System_Config_Value(db_Curser, "gBridge_Trigger", "MQTT", "Port", False)
        self.MQTT_Base_Topic = Get_System_Config_Value(db_Curser, "gBridge_Trigger", "MQTT", "Base Topic", False)

        # Close db connection
        Close_db(db_Connection, db_Curser)

        # Setup the MQTT client for gBridge
        # User / Pass
        self.MQTT_Client.username_pw_set(MQTT_User, MQTT_Pass)
        
        # Enable SSL
        self.MQTT_Client.tls_set_context(context=None)

        # FIX - ADD MQTT Logging
        # self.MQTT_Client.on_log = MQTT_On_Log

        # Callbacks
        self.MQTT_Client.on_connect = self.MQTT_On_Connect
        self.MQTT_Client.on_disconnect = self.MQTT_On_Disconnect

        # Variables to hold MQTT Broker connection statuses
        self.MQTT_Connected_Dobby = False
        self.MQTT_Connected_gBridge = False

        # Connect to broker
        self.MQTT_Client.connect(self.MQTT_Broker, port=MQTT_Port, keepalive=60, bind_address="")

        # Spawn thread for MQTT Client Loop
        MQTTC_Thread = threading.Thread(name='DobbygBridgeMQTTClient', target=self.MQTT_Client_Loop)
        MQTTC_Thread.daemon = True
        MQTTC_Thread.start()

        # Start checker thread
        File_Change_Checker_Thread = threading.Thread(name='DobbygBridgeChecker', target=self.Checker, kwargs={})
        File_Change_Checker_Thread.daemon = True
        File_Change_Checker_Thread.start()


    # From local to gBridge
    def Trigger_Local(self, id, Topic, Payload):
        # Ignore "/set" messages to avoid message loops
        if "/set" in Topic:
            # Log event
            Log("Debug", "gBridge Trigger", str(self.Active_Triggers[id]['Name']), "Ignored - gBridge -> Dobby: " + str(Payload))
            return
        # Publish reply
        self.Publish_Reply(id, Topic, Payload)


    def Publish_Reply(self, id, Topic, Payload):
        
        Payload.replace(";", "")

        # Log event
        Log("Debug", "gBridge Trigger", str(self.Active_Triggers[id]['Name']), "Dobby -> gBridge: " + str(Payload))

        # Temperature
        if Topic.endswith("/Humidity"):
            # Round Payload to nearest 0.5 to make google understand
            Payload = round(float(Payload)*2)/2
            self.MQTT_Client.publish(self.MQTT_Base_Topic + self.Active_Triggers[id]["gBridge id"] + "/tempset-humidity/set", payload=str(Payload), qos=0, retain=False)
        
        # Humidity
        elif Topic.endswith("/Temperature"):
            # Round Payload to nearest 0.5 to make google understand
            Payload = round(float(Payload)*2)/2
            self.MQTT_Client.publish(self.MQTT_Base_Topic + self.Active_Triggers[id]["gBridge id"] + "/tempset-ambient/set", payload=str(Payload), qos=0, retain=False)
        
        # DS18B20
        elif "/DS18B20/" in Topic:
            # Round Payload to nearest 0.5 to make google understand
            Payload = round(float(Payload)*2)/2
            self.MQTT_Client.publish(self.MQTT_Base_Topic + self.Active_Triggers[id]["gBridge id"] + "/tempset-ambient/set", payload=str(Payload), qos=0, retain=False)
        
        # Dimmer
        else:
            if str(Payload) == "0":
                # On Off
                self.MQTT_Client.publish(self.MQTT_Base_Topic + self.Active_Triggers[id]["gBridge id"] + "/onoff/set", payload="0", qos=0, retain=False)
                # Brightness
                self.MQTT_Client.publish(self.MQTT_Base_Topic + self.Active_Triggers[id]["gBridge id"] + "/brightness/set", payload="0", qos=0, retain=False)
            else:
                # On Off
                self.MQTT_Client.publish(self.MQTT_Base_Topic + self.Active_Triggers[id]["gBridge id"] + "/onoff/set", payload="1", qos=0, retain=False)
                # Brightness
                self.MQTT_Client.publish(self.MQTT_Base_Topic + self.Active_Triggers[id]["gBridge id"] + "/brightness/set", payload=str(Payload), qos=0, retain=False)

    
    def MQTT_Subscribe_To(self, MQTT_Client, Topic):
        Log("Debug", "gBridge Trigger", "MQTT", "Subscribing to topic: " + Topic)
        self.MQTT_Client.subscribe(Topic)

    def Local_MQTT_On_Connect(self):
        Log("Debug", "gBridge Trigger", "MQTT", "Connected to local broker")
        self.MQTT_Connected_Dobby = True 
   
    def Local_MQTT_On_Disconnect(self):
        Log("Warning", "gBridge Trigger", "MQTT", "Lost connection to local broker")
        self.MQTT_Connected_Dobby = False
   

    def MQTT_On_Disconnect(self, MQTT_Client, userdata, rc):
        Log("Warning", "gBridge", "MQTT", "Disconnected from broker : " + str(self.MQTT_Broker) + " with result code " + str(rc))
        self.MQTT_Connected_gBridge = False


    def MQTT_On_Connect(self, MQTT_Client, userdata, flags, rc):
        Log("Info", "gBridge Trigger", "MQTT", "Connected to broker " + str(self.MQTT_Broker) + " with result code " + str(rc))
        self.MQTT_Connected_gBridge = True 


    # ---------------------------------------- # On message callbacks - Spawns threads ----------------------------------------
    def MQTT_On_Message_Callback(self, mosq, obj, msg):
 
        Message_Thread = threading.Thread(name='DobbygBridgeOnMessage', target=self.MQTT_On_Message, kwargs={"Topic": msg.topic, "Payload": msg.payload, "Retained": msg.retain})
        Message_Thread.daemon = True
        Message_Thread.start()
        return

    # ---------------------------------------- MQTT On Message ----------------------------------------
    def MQTT_On_Message(self, Topic, Payload, Retained):

        # Ignore "/set" messages to avoid message loops
        if "/set" in Topic:
            return

        # Open db connection
        db_Connection = Open_db("Dobby")
        db_Curser = db_Connection.cursor()
        db_Curser.execute("set autocommit = 1")

        gBridge_id = Topic.replace(self.MQTT_Base_Topic, "")
        gBridge_id = gBridge_id.split("/")
        gBridge_id = gBridge_id[0]

        # Get trigger id
        db_Curser.execute('SELECT id FROM Dobby.`gBridge_Trigger` WHERE `gBridge id`="' + str(gBridge_id) + '";')
        id = db_Curser.fetchone()
        id = id[0]

        # Change Last_Trigger
        db_Curser.execute("UPDATE `Dobby`.`gBridge_Trigger` SET `Triggered DateTime`='" + str(datetime.datetime.now()) + "' WHERE `id`='" + str(id) + "';")

        # Close db connection
        Close_db(db_Connection, db_Curser)

        # Check what kind of message it is
        if "/onoff" in Topic:
            # If its a Dimmer, is 1 set value to 75% to get some light
            if "/Dimmer/" in self.Active_Triggers[id]["MQTT Target"]:
                if Payload == "1":
                    Payload = 75
        
        # Nothing to do here yet
        elif "/brightness" in Topic:
            pass
        elif "/tempset-mode" in Topic:
            pass
        elif "/tempset-setpoint" in Topic:
            pass
        elif "/tempset-ambient" in Topic:
            pass
        elif "/tempset-humidity" in Topic:
            pass
        else:
            Log("Error", "gBridge Trigger", str(self.Active_Triggers[id]['Name']), "Unknown gBridge Topic: " + str(Topic))
            return

        # Publish Message
        MQTT_Client.publish(self.Active_Triggers[id]["MQTT Target"], payload=str(Payload) + ";", qos=0, retain=False)
        # Log event
        Log("Debug", "gBridge Trigger", str(self.Active_Triggers[id]['Name']), "gBridge -> Dobby: " + str(Payload))
        

    def MQTT_Client_Loop(self):
        # Start MQTT Loop
        self.MQTT_Client.loop_forever()

    # ---------------------------------------- Checker ----------------------------------------
    def Checker(self):
        # Start eternal loop
        while True:
            # Wait for MQTT Connections
            while self.MQTT_Connected_Dobby == False and self.MQTT_Connected_gBridge == False:
                # Log event
                Log("Debug", "gBridge Trigger", 'MQTT', "Waiting for connection to MQTT brokers to be established")
                # Delete all triggers
                self.Delete_All_Triggers()
                # Dont sent the message again
                while self.MQTT_Connected_Dobby == False and self.MQTT_Connected_gBridge == False:
                    pass

            # Open db connection get id, Last Modified
            db_Connection = Open_db("Dobby")
            db_Curser = db_Connection.cursor()

            # Get id and Last Modified to check if gBridge Triggers needs to be started
            db_Curser.execute("SELECT id, Last_Modified FROM Dobby.`gBridge_Trigger` WHERE Enabled=1;")

            gBridge_Info = db_Curser.fetchall()
            
            # Close db connection
            Close_db(db_Connection, db_Curser)

            for i in range(len(gBridge_Info)):
                id = gBridge_Info[i][0]
                Last_Modified = gBridge_Info[i][1]

                # Check if the trigger is in the Active_Triggers dict
                if id in self.Active_Triggers:
                    
                    # Check if last modified changed
                    if self.Active_Triggers[id]["Last_Modified"] != Last_Modified:
                        # Deleting the trigger now and then i will get readded in next run, little delay between sub and unsub
                        self.Delete_Trigger(id)
                        
                # If not then add to the list and start the trigger
                else:
                    # Save trigger info
                    self.Add_Trigger(id)
                    # Start the trigger
                    self.Start_Trigger(id)

            # Sleep till next check
            time.sleep(self.Refresh_Rate)

            # if self.Checker_Stop is True:
            #     # Log event
            #     Log("Info", "gBridge Trigger", 'Checker', "Stopping")

            #     # Stop all triggers
            #     for Key, Value in self.Active_Triggers.items():
            #         Key = Key
            #         Log("Debug", "gBridge Trigger", 'Checker', "Removing trigger: " + str(Value['Name']))
            #         # gBridge_Trigger Restart_Trigger(id)

            #     quit()

    def Delete_All_Triggers(self):
        # Stop all triggers
        for id, Info in self.Active_Triggers.items():
            Log("Debug", "gBridge Trigger", 'Checker', "Removing trigger: " + str(Info['Name']))
            self.Delete_Trigger(id)


    def Add_Trigger(self, id):

        # Open db connection
        db_Connection = Open_db("Dobby")
        db_Curser = db_Connection.cursor()

        # Get Name, gBridge id, MQTT Target, Last_Modified
        db_Curser.execute("SELECT Name, `gBridge id`, `MQTT Target`, Last_Modified FROM Dobby.`gBridge_Trigger` WHERE id=" + str(id) + ";")
        gBridge_Info = db_Curser.fetchone()
        
        # Close db connection
        Close_db(db_Connection, db_Curser)

        self.Active_Triggers[id] = {"Name": gBridge_Info[0], "gBridge id": gBridge_Info[1], "MQTT Target": gBridge_Info[2], "Last_Modified": gBridge_Info[3]}


    def Delete_Trigger(self, id):
        # Stop the trigger before deliting
        self.Stop_Trigger(id)

        # Remove triggre from Active_Triggers
        try:
            del self.Active_Triggers[id]
        except KeyError:
            pass


    def Start_Trigger(self, id):

        # Build source topic from base and gbridge id
        Source_Topic = self.MQTT_Base_Topic + self.Active_Triggers[id]["gBridge id"] + "/#"
        
        # Log Event
        Log("Info", "gBridge Trigger", str(self.Active_Triggers[id]["Name"]), "Starting")
        Log("Debug", "gBridge Trigger", str(self.Active_Triggers[id]["Name"]), "Subscribing to: '" + str(Source_Topic) + "'")
        # Subscribe - gBridge
        self.MQTT_Client.subscribe(str(Source_Topic))
        # Register callbacks - gBridge
        self.MQTT_Client.message_callback_add(str(Source_Topic), self.MQTT_On_Message_Callback)

        # Generate Subscribe Topic
        Sub_Topic = str(self.Active_Triggers[id]["MQTT Target"])
        # Temp and humidity
        if "Temperature" in self.Active_Triggers[id]["MQTT Target"]:
            # Do nothing to target topic
            pass
        elif "Humidity" in self.Active_Triggers[id]["MQTT Target"]:
            # Do nothing to target topic
            pass
        # Dont add state if alread there
        elif Sub_Topic.endswith("/State"):
            pass
        # Anything else
        # Remember to add "/State" to get the devices state and not create a message loop
        else:
            Sub_Topic = Sub_Topic + "/State"

        # Add topic to topic dict - Dobby
        MQTT_Add_Sub_Topic(Sub_Topic, 'gBridge Trigger', id)
        # Subscribe - Dobby
        MQTT_Client.subscribe(Sub_Topic)
        # Register callbacks - Dobby
        MQTT_Client.message_callback_add(Sub_Topic, MQTT_On_Message_Callback)


    def Stop_Trigger(self, id):
        # Build source topic from base and gbridge id
        Source_Topic = self.MQTT_Base_Topic + self.Active_Triggers[id][1] + "/#"

         # Log Event
        Log("Debug", "gBridge Trigger", str(id), "Stopping")
        Log("Debug", "gBridge Trigger", str(id), "Unsubscribing from: '" + str(Source_Topic) + "'")

        # Unsubscribe and remove callback
        self.MQTT_Client.unsubscribe(Source_Topic)
        self.MQTT_Client.message_callback_remove(Source_Topic)

        # Unsubscribe and remove callback - local
        MQTT_Del_Sub_Topic(str(self.Active_Triggers[id]["MQTT Target"]), 'Mail Trigger', id)



# ---------------------------------------- KeepAlive Monitor ----------------------------------------
def KeepAlive_Monitor(Topic, Payload, Retained):

    # Ignore retinaed messages
    if Retained is True:
        return

    # Open db connection and create log db if needed
    db_Connection = Open_db("DobbyKeepAliveMonitorLog", True)
    if db_Connection is not None:
        db_Curser = db_Connection.cursor()
        db_Curser.execute("set autocommit = 1")
    # Unable to connect to log db
    else:
        # Log event logged as debug so we dont spam the log
        Log("Debug", "KeepAliveMonitor", "db", "Unable to connect")

    # Check if the message contains a json
    try:
        root_KL = json.loads(Payload)
    except ValueError:
        Log("Warning", "KeepAliveMonitor", "KeepAlive", "From unknown device - Topic: " + Topic + " Payload: " + Payload)
        return
    # Log event
    Log("Debug", "KeepAliveMonitor", root_KL["Hostname"], "Recived keepalive")
    # Check if the json has the values we need
    if "IP" not in root_KL:
        Log("Debug", "KeepAliveMonitor", root_KL["Hostname"], "'IP' not in keepalive")
        if root_KL["Hostname"] is "Dobby":
            root_KL["IP"] = "127.0.0.1"
        else:
            root_KL["IP"] = "0.0.0.0"

    if "RSSI" not in root_KL:
        Log("Debug", "KeepAliveMonitor", root_KL["Hostname"], "'RSSI' not in keepalive")
        root_KL["RSSI"] = "0"

    # if root_KL["Hostname"] != "Dobby":
    #     # Spawn thread for Auto Update Check
    #     AU_Thread = threading.Thread(target=Auto_Update, kwargs={"Hostname": root_KL["Hostname"], "IP": root_KL["IP"], "Current_SW": root_KL["Software"]})
    #     AU_Thread.daemon = True
    #     AU_Thread.start()

    Failed = False
    SQL_String = "INSERT INTO `" + root_KL["Hostname"] + "` (UpFor, FreeMemory, SoftwareVersion, IP, RSSI) VALUES('" + str(root_KL["Uptime"]) + "', '" + str(root_KL["FreeMemory"]) + "', '" + str(root_KL["Software"]) + "', '" + str(root_KL["IP"]) + "', '" + str(root_KL["RSSI"]) + "');"
    # Try to log
    try:
        db_Curser.execute(SQL_String)
    except (MySQLdb.Error, MySQLdb.Warning) as e:
        # 1146 = Table is missing
        if e[0] == 1146:
            # Log event
            Log("Debug", "KeepAliveMonitor", root_KL["Hostname"], "Missing db table creating it")
            try:
                db_Curser.execute("CREATE TABLE `" + root_KL["Hostname"] + "` (`id` INTEGER PRIMARY KEY AUTO_INCREMENT NOT NULL, `LastKeepAlive` timestamp DEFAULT CURRENT_TIMESTAMP NOT NULL, `UpFor` int(11) unsigned NOT NULL, `FreeMemory` DECIMAL(13,0) NOT NULL, `SoftwareVersion` int(6) NOT NULL, `IP` VARCHAR(16) NOT NULL, `RSSI` INT(5) NOT NULL);")
            except (MySQLdb.Error, MySQLdb.Warning) as e:
                # Error 1050 = Table already exists
                # This miight happen if another KeepAliveMonitor process triggered at almost the same time, this is NOT an error
                if e[0] != 1050:
                    Log("Error", "KeepAliveMonitor", root_KL["Hostname"], "db table created")
                    # Try to write log again
                    db_Curser.execute(SQL_String)
                else:
                    Log("Error", "KeepAliveMonitor", root_KL["Hostname"], "db error: " + str(e))
                    Failed = True
        else:
            Log("Error", "KeepAliveMonitor", "db", str(e))
            Failed = True

    # Max entries check
    if Failed == False:
        Table_Size_Check(db_Curser, root_KL["Hostname"], Dobby_Config['Log_Length_KeepAliveMonitor'])

    Close_db(db_Connection, db_Curser)


# ---------------------------------------- MQTT Functions ----------------------------------------
def MQTT_Functions(Payload):
    if ";" in Payload:
        Payload = Payload.replace(";", "")

    Log("Debug", "MQTT Functions", "Recieved", Payload)

    db_Func_Connection = Open_db("Dobby")
    db_Func_Curser = db_Func_Connection.cursor()

    try:
        db_Func_Curser.execute('SELECT Type, Command, DelayAfter FROM `Dobby`.`MQTT_Functions` WHERE Function="' + Payload + '" ORDER BY CommandNumber;')
        Command_List = db_Func_Curser.fetchall()
        Close_db(db_Func_Connection, db_Func_Curser)
    except (MySQLdb.Error, MySQLdb.Warning) as e:
        Log("Critical", "MQTT Functions", "db", "Error: " + str(e[0]) + " - " + str(e[1]))
        return

    if Command_List is ():
        Log("Warning", "MQTT Functions", "Unknown Function", Payload)
        return

    Log("Info", "MQTT Functions", "Executing Function", Payload)

    for Command in Command_List:

        if "MQTT" in Command[0]:
            Publish_String = Command[1].split("&")

            if Publish_String[1][-1:] is not ";":
                MQTT_Client.publish(Publish_String[0], payload=Publish_String[1] + ";", qos=0, retain=False)
            else:
                MQTT_Client.publish(Publish_String[0], payload=Publish_String[1], qos=0, retain=False)

        elif "Audio" in Command[0]:
            # FIX - Add setting in db
            #call(["sudo", "-S", "mpg123", "-a", "btSpeaker", "-g", "50", "/etc/Dobby/Audio/" + Command[1]])
            pass

        if Command[2] != 0:
            # Delay_For = Command[2]
            time.sleep(Command[2])


# ---------------------------------------- # On message callbacks - Spawns threads ----------------------------------------
def MQTT_On_Message_Callback(mosq, obj, msg):
    Message_Thread = threading.Thread(name='DobbygOnMessage', target=MQTT_On_Message, kwargs={"Topic": msg.topic, "Payload": msg.payload, "Retained": msg.retain})
    Message_Thread.daemon = True
    Message_Thread.start()
    return


# ---------------------------------------- MQTT On Message ----------------------------------------
def MQTT_On_Message(Topic, Payload, Retained):

    # Ignore retained messages
    if Retained == True:
        return

    for Target_Topic, Target_Function in dict(MQTT_Topic_Dict).iteritems():

        Do_Something = False

        if "#" in Target_Topic:
            # Check if incomming topic matches the beginning of target topic
            # Remove # from target topic
            Target_Topic = Target_Topic.replace("#", "")

            # if Topic == Target_Topic:
            if Topic[0:len(Target_Topic)] == Target_Topic:
                Do_Something = True

        elif "+" in Target_Topic:
            # Remove # from target topic
            Target_Topic = Target_Topic.replace("+", "")

            # The +1 is = to any char from the mqtt +
            if Topic[0:len(Target_Topic) + 1] == Target_Topic:
                Do_Something = True

        elif Topic == Target_Topic:
            Do_Something = True

        if Do_Something == True:
            # Run each function
            for Function in Target_Function:

                if Function[0] == "KeepAlive":
                    KeepAlive_Monitor(Topic, Payload, Retained)

                elif Function[0] == "Log Trigger":
                    Log_Trigger.On_Message(Function[1], Payload, Retained)

                elif Function[0] == "Alert Trigger":
                    Alert_Trigger.On_Message(Function[1], Payload)

                elif Function[0] == "Action Trigger":
                    Action_Trigger.On_Message(Function[1], Topic, Payload)

                elif Function[0] == "gBridge Trigger":
                    MQTT_Client_gBridge.Trigger_Local(Function[1], Topic, Payload)

                elif Function[0] == "Functions":
                    MQTT_Functions(Payload)

                elif Function[0] == "Commands":
                    MQTT_Commands(Topic, Payload)

                elif Function[0] == "Device Logger":
                    Device_Logger(Topic, Payload, Retained)

                else:
                    # Log event
                    Log("Info", "MQTT Functions", "Missing", str(Function))


# ---------------------------------------- MQTT ----------------------------------------
def MQTT_Add_Sub_Topic(Topic, Function, Options={}):

    if Topic in MQTT_Topic_Dict:
        MQTT_Topic_Dict[Topic].append([Function, Options])
    else:
        MQTT_Topic_Dict[Topic] = [[Function, Options]]

def MQTT_Del_Sub_Topic(Topic, Function, Options={}):

    if Topic in MQTT_Topic_Dict:
        if [Function, Options] in MQTT_Topic_Dict[Topic]:
            MQTT_Topic_Dict[Topic].remove([Function, Options])

def MQTT_Subscribe_To(MQTT_Client, Topic):
    Log("Info", "Dobby", "MQTT", "Subscribing to topic: " + Topic)
    MQTT_Client.subscribe(Topic)


def MQTT_On_Connect(MQTT_Client, userdata, flags, rc):
    Log("Debug", "Dobby", "MQTT", "Connected to broker " + str(Dobby_Config['MQTT_Broker']) + " with result code " + str(rc))

    for Topic in MQTT_Topic_Dict.keys():
        MQTT_Subscribe_To(MQTT_Client, Topic)

        MQTT_Client.message_callback_add(Topic, MQTT_On_Message_Callback)

    # Tell gBridge that we connected
    MQTT_Client_gBridge.Local_MQTT_On_Connect()
    
    # MQTT KeepAlive
    # FIX - CHANGE KEEPALIVE TIMER SOURCE IN DB
    # KeepAlive_Thread = threading.Thread(target=MQTT_KeepAlive_Start, kwargs={"MQTT_Client": MQTT_Client})
    # KeepAlive_Thread.daemon = True
    # KeepAlive_Thread.start()


def MQTT_On_Disconnect(MQTT_Client, userdata, rc):
    Log("Warning", "Dobby", "MQTT", "Disconnected from broker : " + str(Dobby_Config['MQTT_Broker']))
    # Tell gBridge that we disconnected
    MQTT_Client_gBridge.Local_MQTT_On_Disconnect()


def MQTT_On_Log(MQTT_Client, userdata, level, buf):

    # Log level check
    if level == 16:
        if Dobby_Config['Log_Level_MQTT'] == "debug":
            Log("Debug", "MQTT", "Message", buf)

    else:
        Log("Warning", "MQTT", "Message", buf)


# ---------------------------------------- Init ----------------------------------------
def Dobby_init():

    # Open db connection
    db_Connection = Open_db('Dobby')
    if db_Connection is None:
        # Log event
        Log('Fatal', 'System', 'Dobby', "Unable to connect to 'Dobby' db")
        quit()
    db_Curser = db_Connection.cursor()
    
    # Get db config
    # Dobby
    Dobby_Config['System_Header'] = Get_System_Config_Value(db_Curser, "Dobby", "System", "Header")

    # MQTT
    Dobby_Config['MQTT_Broker'] = Get_System_Config_Value(db_Curser, "Dobby", "MQTT", "Broker")
    Dobby_Config['MQTT_Port'] = Get_System_Config_Value(db_Curser, "Dobby", "MQTT", "Port")
    Dobby_Config['MQTT_Username'] = Get_System_Config_Value(db_Curser, "Dobby", "MQTT", "Username")
    Dobby_Config['MQTT_Password'] = Get_System_Config_Value(db_Curser, "Dobby", "MQTT", "Password")
    Dobby_Config['MQTT_Publish_Delay'] = float(Get_System_Config_Value(db_Curser, "Dobby", "MQTT", "PublishDelay"))
    Dobby_Config['MQTT_KeepAlive_Interval'] = int(Get_System_Config_Value(db_Curser, "Dobby", "MQTTKeepAlive", "Interval"))

    # Email
    Dobby_Config['Mail_Trigger_SMTP_Server'] = Get_System_Config_Value(db_Curser, "Mail_Trigger", "SMTP", "Server")
    Dobby_Config['Mail_Trigger_SMTP_Port'] = Get_System_Config_Value(db_Curser, "Mail_Trigger", "SMTP", "Port")
    Dobby_Config['Mail_Trigger_SMTP_Sender'] = Get_System_Config_Value(db_Curser, "Mail_Trigger", "SMTP", "Sender")
    Dobby_Config['Mail_Trigger_SMTP_Username'] = Get_System_Config_Value(db_Curser, "Mail_Trigger", "SMTP", "Username")
    Dobby_Config['Mail_Trigger_SMTP_Password'] = Get_System_Config_Value(db_Curser, "Mail_Trigger", "SMTP", "Password")

    Dobby_Config['Log_db'] = Get_System_Config_Value(db_Curser, "Dobby", "Log", "db")
    Dobby_Config['Log_Level_System'] = Get_System_Config_Value(db_Curser, "Dobby", "Log", "Level").lower()

    Dobby_Config['Log_Length_System'] = int(Get_System_Config_Value(db_Curser, "Dobby", "Log", "Length"))

    # Device Logger
    Dobby_Config['Log_Length_Device_Logger'] = int(Get_System_Config_Value(db_Curser, "Device Logger", "Log", "Length", QuitOnError=False, Error_Value=10000))

    # MQTT
    Dobby_Config['Log_Level_MQTT'] = Get_System_Config_Value(db_Curser, "MQTT", "Log", "Level", QuitOnError=False).lower()

    # From KeepAliveMonitor
    Dobby_Config['Log_Level_KeepAliveMonitor'] = Get_System_Config_Value(db_Curser, "KeepAliveMonitor", "Log", "Level", QuitOnError=False, Error_Value="Info").lower()
    Dobby_Config['Log_Length_KeepAliveMonitor'] = int(Get_System_Config_Value(db_Curser, "KeepAliveMonitor", "Log", "Length", QuitOnError=False, Error_Value=21600))

    # From MQTTConfig
    Dobby_Config['Log_Level_MQTT_Config'] = Get_System_Config_Value(db_Curser, "Device Config", "Log", "Level", QuitOnError=False).lower()

    # From MQTT Functions
    Dobby_Config['Log_Level_MQTT_Functions'] = Get_System_Config_Value(db_Curser, "MQTT Functions", "Log", "Level", QuitOnError=False).lower()

    # Mail_Trigger
    Dobby_Config['Log_Level_Mail_Trigger'] = Get_System_Config_Value(db_Curser, "Mail_Trigger", "Log", "Level", QuitOnError=False).lower()

    # Log_Trigger
    Dobby_Config['Log_Level_Log_Trigger'] = Get_System_Config_Value(db_Curser, "Log_Trigger", "Log", "Level", QuitOnError=False).lower()

    # Spammer
    Dobby_Config['Log_Level_Spammer'] = Get_System_Config_Value(db_Curser, "Spammer", "Log", "Level", QuitOnError=False).lower()

    # APC_Monitor
    Dobby_Config['Log_Level_APC_Monitor'] = Get_System_Config_Value(db_Curser, "APC_Monitor", "Log", "Level", QuitOnError=False).lower()
    
    # # Backup
    # Dobby_Config['Backup_URL_FTP'] = Get_System_Config_Value(db_Curser, "Backup", "URL", "FTP", QuitOnError=False).lower()
    
    # Close db connection
    Close_db(db_Connection, db_Curser)
    # Log event
    Log('Debug', 'System', 'Logging', "Changing to db logging, to see log in console, run Dobby.py with '--verbose'")
    # Set Dobby_Configred to true, this will make loggin save the log to db and stop printing to terminal
    Dobby_Config['Init'] = True

    # Append Topics to subscribe to subscribe list
    # Log
    MQTT_Add_Sub_Topic(Dobby_Config['System_Header'] + "/Log/#", 'Device Logger')
    # KeepAlive
    MQTT_Add_Sub_Topic(Dobby_Config['System_Header'] + "/KeepAlive/#", 'KeepAlive')
    # Functions
    MQTT_Add_Sub_Topic(Dobby_Config['System_Header'] + "/Functions", 'Functions')
    # Dobby Commands
    MQTT_Add_Sub_Topic(Dobby_Config['System_Header'] + "/Commands/Dobby/#", 'Commands')


def MQTT_init():
    # MQTT Setup
    MQTT_Client.username_pw_set(Dobby_Config['MQTT_Username'], Dobby_Config['MQTT_Password'])
    # FIX - ADD MQTT Logging
    MQTT_Client.on_log = MQTT_On_Log

    # Callbacks
    MQTT_Client.on_connect = MQTT_On_Connect
    MQTT_Client.on_disconnect = MQTT_On_Disconnect

    # Connect to broker
    MQTT_Client.connect(Dobby_Config['MQTT_Broker'], port=Dobby_Config['MQTT_Port'], keepalive=60, bind_address="")

    # Boot message - MQTT
    MQTT_Client.publish(Dobby_Config['System_Header'] + "/Log/Dobby/Info/System", payload="Booting Dobby - Version: " + str(Version), qos=0, retain=False)



# # ---------------------------------------- MQTT Target Check ----------------------------------------
# class MQTT_Target_Check():

#     Check_Delay = 0.500
    
#     def __init__(self):
#         # Log event
#         Log("Debug", "System", "MQTT Target Check", "Initializing")

#         # Create vars
#         self.Check_At = datetime.datetime.now()
#         self.MQTT_Target = ""
#         self.Delete_Me = False
#         self.Triggered = True

#         # Start timeout
#         Timer_Thread = threading.Thread(target=self.Run)
#         Timer_Thread.daemon = True
#         Timer_Thread.start()

#     def Reset(self, MQTT_Target, Expected_Value, Force_Change=True):
#         # Log event
#         Log("Debug", "System", "MQTT Target Check", "Reset alert id: " + str(MQTT_Target))
        
#         # Save vars
#         self.MQTT_Target = MQTT_Target
#         ## Add timeout to current time to get Timeout_At
#         self.Timeout_At = datetime.datetime.now() + datetime.timedelta(seconds=self.Timeout)
#         ## Alert id
#         self.MQTT_Target = MQTT_Target

#         # Reset triggered
#         self.Triggered = False
        

#     def Delete(self):
#         Log("Debug", "System", "MQTT Target Check", "Deleted alert id: " + str(self.MQTT_Target))
#         # Mark thread for deletions
#         self.Delete_Me = True


#     def Trigger_Timeout(self):
#         if self.Triggered == True:
#             return
        
#         # Set var to prevent retrigger
#         self.Triggered = True

#         # Log event
#         Log("Debug", "System", "MQTT Target Check", "Triggered alert id:" + str(self.Alert_Target_id))
        
#         # Get alert information from db        
#         ## Open db connection
#         db_Connection = Open_db("Dobby")
#         db_Curser = db_Connection.cursor()
#         # Set autocommit so no delay on saving changes
#         db_Curser.execute("set autocommit = 1")

#         ## Get id and Last Modified to check if gBridge Triggers needs to be started
#         db_Curser.execute("SELECT `Mail Target`, `MQTT Target`, `Push Target`, Subject, Body FROM Dobby.`Alert_Targets` WHERE id=" + str(self.Alert_Target_id) + ";")
#         Alert_Info = db_Curser.fetchone()

#         # Change Last_Trigger
#         db_Curser.execute("UPDATE `Dobby`.`Alert_Targets` SET `Last_Trigger`='" + str(datetime.datetime.now()) + "' WHERE `id`='" + str(id) + "';")

#         ## Close db connection
#         Close_db(db_Connection, db_Curser)

#         # Send Alerts
#         ## 0 = Mail Target
#         ## 1 = MQTT Target
#         ## 2 = Push Target
#         ## 3 = Subject
#         ## 4 = Body
#         print "fix mqtt target check"
#         # Send_Alert(Alert_Info[3], Alert_Info[4], None, Alert_Info[0], Alert_Info[1], Alert_Info[2])


#     def Run(self):
#         # Just sleep untill id is set
#         while self.Alert_Target_id == "" and self.Delete_Me == False:
#             # Sleep untill next check
#             time.sleep(self.Check_Delay)

#         # When id is set start the timeout
#         while self.Delete_Me == False:
 
#             # Check if current time vs timeout at time
#             if self.Timeout_At < datetime.datetime.now():
#                 self.Trigger_Timeout()

#             # Sleep untill next check
#             time.sleep(self.Check_Delay)


    

# ---------------------------------------- Send Mail ----------------------------------------
def Send_Mail(To, Subject, Text):
    # Remove any spaces
    To = To.replace(" ", "")

    Target_List = []

    # Multiple targets
    if "," in To:
        Target_List = To.split(",")

    # Single target
    else:
        Target_List.append(To)

    Mail_Body = "\r\n".join([
        "From: " + str(Dobby_Config['Mail_Trigger_SMTP_Sender']),
        "To: " + To,
        "Subject: " + str(Subject),
        "",
        str(Text)
    ])


    # Connect to mail server
    Mail_Server = smtplib.SMTP(Dobby_Config['Mail_Trigger_SMTP_Server'], Dobby_Config['Mail_Trigger_SMTP_Port'])
    Mail_Server.ehlo()
    Mail_Server.starttls()
    Mail_Server.login(Dobby_Config['Mail_Trigger_SMTP_Username'], Dobby_Config['Mail_Trigger_SMTP_Password'])

    # Send Email
    for To_Email in Target_List:
        Mail_Server.sendmail(Dobby_Config['Mail_Trigger_SMTP_Sender'], To_Email, str(Mail_Body))
        Log("Debug", "System", "Mail", 'Send mail to: ' + str(To_Email))

    # Disconnect from mail server
    Mail_Server.quit()


# ---------------------------------------- Send Push ----------------------------------------
def Send_Push(Target, Subject, Message):
    # Remove any spaces
    Target = Target.replace(" ", "")

    Target_List = []

    # Multiple targets
    if "," in Target:
        Target_List = Target.split(",")

    # Single target
    else:
        Target_List.append(Target)

    # Generate the URL needed for the request
    URL_End = "&title=" + str(Subject) + "&message=" + str(Message) + "&type=Alert"
    URL_End = URL_End.replace(" ", "%20")

    # Send Push Notification 
    for Target_Push in Target_List:
        URL = "https://wirepusher.com/send?id=" + str(Target_Push) + URL_End
        Log("Debug", "System", "Push", 'Get URL: ' + URL)
        r = requests.get(URL)
        r.status_code
        Log("Debug", "System", "Push", 'Status: ' + str(r.status_code))


# ---------------------------------------- Alert Trigger ----------------------------------------
class Alert_Trigger():
    # How often the db is cheched for changes
    Refresh_Rate = 5

    Active_Triggers = {}

    def __init__(self):
        # Log event
        Log("Info", "Alert Trigger", "Checker", "Initializing")

        # Start checker thread
        File_Change_Checker_Thread = threading.Thread(name='DobbyAlertTriggerChecker', target=self.Checker, kwargs={})
        File_Change_Checker_Thread.daemon = True
        File_Change_Checker_Thread.start()

    def Checker(self):
        # Start eternal loop
        while True:
            # Open db connection get id, Last Modified
            db_Connection = Open_db("Dobby")
            db_Curser = db_Connection.cursor()

            # Get id and Last Modified to check if Alert Triggers needs to be started
            db_Curser.execute("SELECT id, Last_Modified FROM Dobby.`Alert_Trigger` WHERE Enabled=1;")
            Alert_Info = db_Curser.fetchall()

            for i in range(len(Alert_Info)):
                # Alert_Info[i][0] - id
                # Alert_Info[i][1] - Last Modified

                # Check if the trigger is in the Active_Triggers dict
                if Alert_Info[i][0] in self.Active_Triggers:
                    
                    # Check if last modified changed
                    if self.Active_Triggers[Alert_Info[i][0]] != Alert_Info[i][1]:
                        self.Active_Triggers[Alert_Info[i][0]] = Alert_Info[i][1]
                        self.Restart_Trigger(Alert_Info[i][0])
                        
                # If not add then to the list and start the trigger
                else:
                    self.Active_Triggers[Alert_Info[i][0]] = Alert_Info[i][1]
                    # Start the trigger
                    self.Start_Trigger(Alert_Info[i][0])

            # Close db connection
            Close_db(db_Connection, db_Curser)

            # Sleep till next check
            time.sleep(self.Refresh_Rate)
    

    def Start_Trigger(self, id):

        Trigger_Info = self.Get_Trigger_Info(id)

        # Log Event
        Log("Debug", "Alert Trigger", str(Trigger_Info[0]), "Starting")
        Log("Debug", "Alert Trigger", str(Trigger_Info[0]), "Subscribing to: '" + str(Trigger_Info[1]) + "'")
        # Add topic to topic tict
        MQTT_Add_Sub_Topic(str(Trigger_Info[1]), 'Alert Trigger', id)
        # Subscribe
        MQTT_Client.subscribe(str(Trigger_Info[1]))
        # Register callbacks
        MQTT_Client.message_callback_add(str(Trigger_Info[1]), MQTT_On_Message_Callback)


    def Stop_Trigger(self, id):

        Trigger_Info = self.Get_Trigger_Info(id)

         # Log Event
        Log("Debug", "Alert Trigger", str(Trigger_Info[0]), "Stopping")
        Log("Debug", "Alert Trigger", str(Trigger_Info[0]), "Unsubscribing from: '" + str(Trigger_Info[1]) + "'")

        MQTT_Del_Sub_Topic(Trigger_Info[1], 'Alert Trigger', id)


    def Restart_Trigger(self, id):
        self.Start_Trigger(id)
        self.Stop_Trigger(id)


    def Get_Trigger_Info(self, id):
        # Open db connection
        db_Connection = Open_db("Dobby")
        db_Curser = db_Connection.cursor()

        db_Curser.execute("SELECT Name, `MQTT Target` FROM Dobby.`Alert_Trigger` WHERE id="+ str(id) + ";")
        Trigger_Info = db_Curser.fetchone()
        # Trigger_Info[0] - Name
        # Trigger_Info[1] - Target

        # Close db connection
        Close_db(db_Connection, db_Curser)

        # Return info
        return Trigger_Info


    @classmethod
    def On_Message(cls, id, Payload):

        db_Connection = Open_db("Dobby")
        db_Curser = db_Connection.cursor()

        db_Curser.execute("set autocommit = 1")

        db_Curser.execute("SELECT Name, `Alert State`, `MQTT Payload Clear`, `MQTT Payload Trigger`, `Alert Target id`, `Alert Subject`, `Alert Payload Clear`, `Alert Payload Trigger` FROM Dobby.Alert_Trigger WHERE id=" + str(id) + ";")
        Trigger_Info = db_Curser.fetchone()
           
        Name = Trigger_Info[0]
        Alert_State = Trigger_Info[1]
        MQTT_Payload_Clear = Trigger_Info[2]
        MQTT_Payload_Trigger = Trigger_Info[3]
        Alert_Target_id = Trigger_Info[4]
        Alert_Subject = Trigger_Info[5]
        Alert_Payload_Clear = Trigger_Info[6]
        Alert_Payload_Trigger = Trigger_Info[7]

        # Find out what to do
        Action = 2
        # 0 = Clear
        # 1 = Trigger
        # 2 = In-between

        Trigger_Change = False

        if Payload.endswith(";"):
            Payload = Payload[:-1]

        if float(MQTT_Payload_Clear) == float(MQTT_Payload_Trigger):
            Log("Error", "Alert Trigger", str(Name), 'Clear and Trigger payload is the same value')
            Close_db(db_Connection, db_Curser)
            return

        # High / Low Check
        # Value moving from Low to High
        elif (float(MQTT_Payload_Clear) <= float(MQTT_Payload_Trigger)) is True:
            # Clear check
            if float(MQTT_Payload_Clear) >= float(Payload):
                Action = 0

            # Trigger check
            elif float(MQTT_Payload_Trigger) <= float(Payload):
                Action = 1

        # Value moving from High to Low
        else:
            # Clear check
            if float(MQTT_Payload_Clear) <= float(Payload):
                Action = 0

            # Trigger check
            elif float(MQTT_Payload_Trigger) >= float(Payload):
                Action = 1

        # Take action if needed
        # Clear
        if Action == 0:
            # Check agains current alert state
            if Action == Alert_State:
                Log("Debug", "Alert Trigger", str(Name), 'Already cleared ignoring new clear value: ' + str(Payload))
            else:
                Trigger_Change = True

                # Send Alert Notification
                Send_Alert(Alert_Target_id, Payload, Alert_Subject, Alert_Payload_Clear)
                Log("Info", "Alert Trigger", str(Name), 'Cleared at: ' + str(Payload) + " Target: " + str(MQTT_Payload_Clear))

        # Trigger
        elif Action == 1:
            # Check agains current alert state
            if Action == Alert_State:
                Log("Debug", "Alert Trigger", str(Name), 'Already triggered ignoring new trigger value: ' + str(Payload))
            else:
                Trigger_Change = True

                # Send Alert Notification 
                Send_Alert(Alert_Target_id, Payload, Alert_Subject, Alert_Payload_Trigger)
                Log("Info", "Alert Trigger", str(Name), 'Triggered at: ' + str(Payload) + " Target: " + str(MQTT_Payload_Trigger))

        # In-between value
        elif Action == 2:
            Log("Debug", "Alert Trigger", str(Name), 'In-between value received: ' + str(Payload))

        if Trigger_Change is True:
            # Change Alert_State
            db_Curser.execute("UPDATE `Dobby`.`Alert_Trigger` SET `Alert State`='" + str(Action) + "' WHERE `id`='" + str(id) + "';")
            # Update Triggered_DateTime
            db_Curser.execute("UPDATE `Dobby`.`Alert_Trigger` SET `Triggered DateTime`='" + str(datetime.datetime.now()) + "' WHERE `id`='" + str(id) + "';")

        Close_db(db_Connection, db_Curser)

# ---------------------------------------- Spammer ----------------------------------------
class Spammer:

    # How often does esch spammer read write to the db (sec)
    db_Refresh_Rate = 5
    Loop_Delay = 0.500

    def __init__(self):
        # Log event
        Log("Info", "Spammer", "Checker", "Starting")

        self.Spammer_Dict = {}

        # Start checker thread
        Spammer_Thread = threading.Thread(name='DobbySpammerChecker', target=self.Checker, kwargs={})
        Spammer_Thread.daemon = True
        Spammer_Thread.start()

    def Checker(self):

        while True:
            db_Connection = Open_db("Dobby")
            db_Curser = db_Connection.cursor()

            db_Curser.execute("SELECT id, Last_Modified FROM Dobby.Spammer")
            Spammer_db = db_Curser.fetchall()

            Close_db(db_Connection, db_Curser)

            for i in Spammer_db:
                # i[0] = Spammer db id
                if i[0] not in self.Spammer_Dict:
                    self.Spammer_Dict[i[0]] = self.Agent(i[0])
                    Log("Debug", "Spammer", "Checker", "Starting: " + self.Spammer_Dict[i[0]].Name)

                else:
                    # Change to spammer
                    if str(self.Spammer_Dict[i[0]].Last_Modified) != str(i[1]):
                        Log("Debug", "Spammer", "Checker", "Change found in: " + self.Spammer_Dict[i[0]].Name + " restarting agent")
                        # Wait for agent to close db connection
                        while self.Spammer_Dict[i[0]].OK_To_Kill is False:
                            time.sleep(0.100)

                        # Delete agent
                        Log("Debug", "Spammer", "Checker", "Deleting: " + self.Spammer_Dict[i[0]].Name)
                        del self.Spammer_Dict[i[0]]
                        # Start agent again
                        self.Spammer_Dict[i[0]] = self.Agent(i[0])
                        Log("Debug", "Spammer", "Checker", "Starting: " + self.Spammer_Dict[i[0]].Name)

                time.sleep(random.uniform(0.150, 0.500))

            time.sleep(Spammer.db_Refresh_Rate)

    class Agent:
        def __init__(self, id):

            self.id = int(id)

            db_Connection = Open_db("Dobby")
            db_Curser = db_Connection.cursor()

            db_Curser.execute("SELECT Name, Enabled, `Interval`, Topic, Payload, Next_Ping, Last_Modified FROM Dobby.Spammer WHERE id='" + str(self.id) + "'")
            Spammer_Info = db_Curser.fetchone()

            Close_db(db_Connection, db_Curser)

            self.Name = str(Spammer_Info[0])

            # Can't log event before now if you want to use name
            Log("Debug", "Spammer", self.Name, 'Initializing')

            self.Enabled = bool(Spammer_Info[1])
            self.Interval = float(Spammer_Info[2])
            self.Topic = Spammer_Info[3]
            self.Payload = Spammer_Info[4]
            self.Next_Ping = Spammer_Info[5]
            self.Last_Modified = Spammer_Info[6]
            
            if self.Enabled == 0:
                Log("Debug", "Spammer", self.Name, 'Disabled - Not starting agent')
                quit()
            self.OK_To_Kill = True
            self.Kill = False

            Log("Debug", "Spammer", self.Name, 'Initialization compleate')

            self.Start()

        # ========================= Agent - Start =========================
        def Start(self):
            Spammer_Thread = threading.Thread(name='DobbySpammer', target=self.Run, kwargs={})
            Spammer_Thread.daemon = True
            Spammer_Thread.start()

        # ========================= Agent - Run =========================
        def Run(self):

            Log("Info", "Spammer", self.Name, "Running")
            # Start eternal loop
            while True:
                # Check if its time to ping
                if self.Next_Ping < datetime.datetime.now():
                    Log("Debug", "Spammer", self.Name, "Ping")

                    self.Next_Ping = datetime.datetime.now() + datetime.timedelta(seconds=self.Interval)

                    self.OK_To_Kill = False

                    db_Connection = Open_db("Dobby")
                    db_Curser = db_Connection.cursor()

                    db_Curser.execute("UPDATE `Dobby`.`Spammer` SET `Next_Ping`='" + str(self.Next_Ping) + "', `Last_Ping`='" + str(datetime.datetime.now()) + "' WHERE id = '" + str(self.id) + "';")

                    Close_db(db_Connection, db_Curser)

                    self.OK_To_Kill = True

                    MQTT_Client.publish(self.Topic, payload=self.Payload, qos=0, retain=False)

                    time.sleep(Spammer.Loop_Delay)

                while self.Next_Ping > datetime.datetime.now():
                    time.sleep(Spammer.Loop_Delay)

                if self.Kill is True:
                    quit()


# ---------------------------------------- Device Logger ----------------------------------------
def Device_Logger(Topic, Payload, Retained):

    # Ignore retinaed messages
    if Retained is True:
        return

    # Get device name
    Device_Name = Topic.split("/")
    Device_Name = str(Device_Name[3])

    Failed = False
    
    # Open db connection and create log db if needed
    db_Connection = Open_db("DobbyDeviceLog", True)
    if db_Connection is not None:
        db_Curser = db_Connection.cursor()
        db_Curser.execute("set autocommit = 1")
    # Unable to connect to log db
    else:
        # Log event
        Log("Debug", "Device Logger", "db", "Unable to connect")
        Failed = True
    # Try to log
    try:
        db_Curser.execute('INSERT INTO `DobbyDeviceLog`.`' + Device_Name + '` (Topic, Payload) VALUES("' + Topic + '", "' + Payload + '");')
    except (MySQLdb.Error, MySQLdb.Warning) as e:
        # 1146 = Table is missing
        if e[0] == 1146:
            # Log event
            Log("Debug", "Device Logger", Device_Name, "Missing db table creating it")
            try:
                db_Curser.execute("CREATE TABLE `DobbyDeviceLog`.`" + Device_Name + "` (`id` int(11) NOT NULL AUTO_INCREMENT, `DateTime` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP, `Topic` varchar(75) NOT NULL, `Payload` varchar(200) NOT NULL, PRIMARY KEY (`id`))")
            except (MySQLdb.Error, MySQLdb.Warning) as e:
                # Error 1050 = Table already exists
                # This miight happen if another device logger process triggered at almost the same time, this is NOT an error
                if e[0] != 1050:
                    Log("Error", "Device Logger", Device_Name, "db table created")
                    # Try to write log again
                    db_Curser.execute('INSERT INTO `DobbyDeviceLog`.`' + Device_Name + '` (Topic, Payload) VALUES("' + Topic + '", "' + Payload + '");')
                else:
                    Log("Error", "Device Logger", Device_Name, "db error: " + str(e))
                    Failed = True
        else:
            Log("Error", "Device Logger", "db", str(e))
            Failed = True

    # Max entries check
    if Failed == False:
        Table_Size_Check(db_Curser, Device_Name, Dobby_Config['Log_Length_Device_Logger'])


    # Close db connection
    Close_db(db_Connection, db_Curser)



# ---------------------------------------- EP Logger ----------------------------------------
class EP_Logger:

    # How often does esch EP_Logger read write to the db (sec)
    db_Refresh_Rate = 5
    Loop_Delay = 3

    def __init__(self):
        # Log event
        Log("Info", "EP Logger", "Checker", "Starting")

        self.EP_Logger_Dict = {}

        # Start checker thread
        EP_Logger_Thread = threading.Thread(name='DobbyEPLoggerChecker', target=self.Checker, kwargs={})
        EP_Logger_Thread.daemon = True
        EP_Logger_Thread.start()

    def Checker(self):

        while True:
            db_Connection = Open_db("Dobby")
            db_Curser = db_Connection.cursor()

            db_Curser.execute("SELECT id, Last_Modified FROM Dobby.EP_Logger")
            EP_Logger_db = db_Curser.fetchall()

            Close_db(db_Connection, db_Curser)

            for i in EP_Logger_db:
                # i[0] = EP_Logger db id
                if i[0] not in self.EP_Logger_Dict:
                    self.EP_Logger_Dict[i[0]] = self.Agent(i[0])
                    Log("Debug", "EP Logger", "Checker", "Starting: " + self.EP_Logger_Dict[i[0]].Name)

                else:
                    # Change to EP_Logger
                    if str(self.EP_Logger_Dict[i[0]].Last_Modified) != str(i[1]):
                        Log("Debug", "EP Logger", "Checker", "Change found in: " + self.EP_Logger_Dict[i[0]].Name + " restarting agent")
                        # Wait for agent to close db connection
                        while self.EP_Logger_Dict[i[0]].OK_To_Kill is False:
                            time.sleep(0.100)

                        # Delete agent
                        Log("Debug", "EP Logger", "Checker", "Deleting: " + self.EP_Logger_Dict[i[0]].Name)
                        del self.EP_Logger_Dict[i[0]]
                        # Start agent again
                        self.EP_Logger_Dict[i[0]] = self.Agent(i[0])
                        Log("Debug", "EP Logger", "Checker", "Starting: " + self.EP_Logger_Dict[i[0]].Name)

                time.sleep(random.uniform(0.150, 0.500))

            time.sleep(EP_Logger.db_Refresh_Rate)

    class Agent:
        def __init__(self, id):

            self.id = int(id)
            # Dict to store read value and check agains publish values, to prevent republishing of same value
            self.Value_Dict = {}

            db_Connection = Open_db("Dobby")
            db_Curser = db_Connection.cursor()

            db_Curser.execute("SELECT Name, Enabled, `Serial Port`, `Log Rate`, `Next Ping`, `Last Ping`, Last_Modified FROM Dobby.EP_Logger WHERE id='" + str(self.id) + "'")
            EP_Logger_Info = db_Curser.fetchone()

            Close_db(db_Connection, db_Curser)

            self.Name = str(EP_Logger_Info[0])
            self.Enabled = bool(EP_Logger_Info[1])
            self.Serial_Port = EP_Logger_Info[2]
            self.Log_Rate = EP_Logger_Info[3]
            self.Next_Ping = EP_Logger_Info[4]
            self.Last_Ping = EP_Logger_Info[5]
            self.Last_Modified = EP_Logger_Info[6]


            # Can't log event before now if you want to use name
            Log("Debug", "EP Logger", self.Name, 'Initializing')

            # Check if serial port exists
            try:
                os.stat(self.Serial_Port)
            except OSError:
                Log("Error", "EP Logger", self.Name, 'Serial port: ' + str(self.Serial_Port) + " does not exist. Quitting. Check the driver")
                quit()
            
            # Create the Modbus client
            self.EP_Logger_Client = pyModbus.ModbusSerialClient(method = 'rtu', port = self.Serial_Port, baudrate = 115200)            
            
            if self.Enabled == 0:
                Log("Debug", "EP Logger", self.Name, 'Disabled - Not starting agent')
                quit()
            self.OK_To_Kill = True
            self.Kill = False

            Log("Debug", "EP Logger", self.Name, 'Initialization compleate')

            self.Start()

        # ========================= Agent - Start =========================
        def Start(self):
            EP_Logger_Thread = threading.Thread(name='DobbyEPLogger', target=self.Run, kwargs={})
            EP_Logger_Thread.daemon = True
            EP_Logger_Thread.start()


        # ========================= Agent - Read Input =========================
        def Read_Input(self, Address, Count=1):

            Address = int(str(Address), 16)

            Modbus_Value = ""

            try:
                Modbus_Value = self.EP_Logger_Client.read_input_registers(Address, Count, unit=1)
            except (pyModbus.ConnectionException):
                Log("Debug", "EP Logger", self.Name, "Error reading: " + str(Address) + " Count: " + str(Count))

            return Modbus_Value

        # ========================= Agent - Run =========================
        def Run(self):

            # Make the Modbus client connect and check if we got connected
            if self.EP_Logger_Client.connect() == False:
                # Log event
                Log("Error", "EP Logger", self.Name, "Unable to connect to Modbus quitting.")
                quit()
        
            # Log event
            Log("Info", "EP Logger", self.Name, "Running")

            # Eternal loop
            while True:
                # Check if its time to ping
                if self.Next_Ping < datetime.datetime.now():
                    Log("Debug", "EP Logger", self.Name, "Ping")

                    # Check if connection is up
                    if self.EP_Logger_Client.connect() == False:
                        # Log event
                        Log("Error", "EP Logger", self.Name, "Modbus connection lost quitting.")
                        quit()

                    self.Next_Ping = datetime.datetime.now() + datetime.timedelta(seconds=self.Log_Rate)

                    self.OK_To_Kill = False

                    db_Connection = Open_db("Dobby")
                    db_Curser = db_Connection.cursor()

                    db_Curser.execute("set autocommit = 1")
                    
                    # Get row names
                    db_Curser.execute("SELECT `COLUMN_NAME` FROM `INFORMATION_SCHEMA`.`COLUMNS` WHERE `TABLE_SCHEMA`='Dobby' AND `TABLE_NAME`='EP_Logger';")
                    EP_Logger_Info_Names = db_Curser.fetchall()
                
                    # Get row values
                    db_Curser.execute("SELECT * FROM Dobby.EP_Logger WHERE id = '" + str(self.id) + "';")
                    EP_Logger_Info_Values = db_Curser.fetchone()

                    # Update next / last ping
                    db_Curser.execute("UPDATE `Dobby`.`EP_Logger` SET `Next Ping`='" + str(self.Next_Ping) + "', `Last Ping`='" + str(datetime.datetime.now()) + "' WHERE id = '" + str(self.id) + "';")
                    
                    Close_db(db_Connection, db_Curser)

                    Ignore_List = ['id', 'Name', 'Enabled', 'Serial Port', 'Log Rate', 'Next Ping', 'Last Ping', 'Last_Modified']

                    # List containg lists with tree values name, modbus id, multiplier
                    Modbud_id_List = []

                    for i in range(len(EP_Logger_Info_Names)):

                        if EP_Logger_Info_Names[i][0] in Ignore_List:
                            continue

                        if EP_Logger_Info_Values[i] is 0:
                            continue

                        id_Dict = {}

                        id_Dict['Multiplier'] = 1

                        Test_List = ['Amp', 'Volt', "Watt", "Temperature"]

                        for Test_Name in Test_List:
                            if Test_Name in EP_Logger_Info_Names[i][0]:
                                id_Dict['Multiplier'] = 0.01
                                break

                        id_Dict['Name'] = EP_Logger_Info_Names[i][0][:-7]
                        id_Dict['id'] = EP_Logger_Info_Names[i][0][-6:]

                        Modbud_id_List.append(id_Dict)

                    # Request values
                    for Info in Modbud_id_List:

                        # Read input value
                        ## 0x3200 and 0x3201 needs to read two units
                        if Info['Name'] in {'Battery Status', 'Charger Status'}:
                            Modbus_Value = self.Read_Input(Info['id'], 2)
                        else:
                            Modbus_Value = self.Read_Input(Info['id'])

                        # Check for errors
                        # Not pritty but it works
                        if str(type(Modbus_Value)) == "<class 'pymodbus.exceptions.ModbusIOException'>":
                            # Log event
                            Log("Debug", "EP Logger", "Modbus", "Unable to read: " + Info['Name'] + " - " + str(Modbus_Value))
                            continue

                        # Battery Status
                        if Info['Name'] == 'Battery Status':

                            # D3-D0: 
                            # 00H Normal 
                            # 01H Overvolt 
                            # 02H Under Volt
                            # 03H Low Volt Disconnect
                            # 04H Fault 

                            # D7-D4: 
                            # 00H Normal
                            # 01H Over Temp.(Higher than the warning settings)
                            # 02H Low Temp.( Lower than the warning settings), 

                            # D8: 
                            # normal 0 
                            # Battery inerternal resistance abnormal 1, 

                            # D15: 
                            # 1-Wrong identification for rated voltage
                            
                            # https://www.oipapio.com/question-5355673
                            # No clue how this works but it seems to do so will take it 

                            # Define each mask as a tuple with all the bit at 1 and distance from the right:
                            D3_D0_mask = (0b1111, 0)
                            D7_D4_mask = (0b1111, 4)
                            D8_mask = (0b1, 8)
                            D15_mask = (0b1, 15)

                            # Creating the json dict with all values as false
                            json_State = {}
                            json_State["Fault"] = False
                            json_State["Low Volt Disconnect"] = False
                            json_State["Under Volt"] = False
                            json_State["Overvolt"] = False
                            json_State["Normal Voltage"] = False
                            json_State["Low Temp"] = False
                            json_State["Over Temp"] = False
                            json_State["Normal Temp"] = False
                            json_State["Battery internal resistance abnormal"] = False
                            json_State["Wrong identification for rated voltage"] = False

                            # compare each mask to the value, after shifting to the right position:
                            # Update values to true if so
                            if D3_D0_mask[0]&(Modbus_Value.registers[0]>>D3_D0_mask[1]) == 4:
                                json_State["Fault"] = True
                            if D3_D0_mask[0]&(Modbus_Value.registers[0]>>D3_D0_mask[1]) == 3:
                                json_State["Low Volt Disconnect"] = True
                            if D3_D0_mask[0]&(Modbus_Value.registers[0]>>D3_D0_mask[1]) == 2:
                                json_State["Under Volt"] = True
                            if D3_D0_mask[0]&(Modbus_Value.registers[0]>>D3_D0_mask[1]) == 1:
                                json_State["Overvolt"] = True
                            if D3_D0_mask[0]&(Modbus_Value.registers[0]>>D3_D0_mask[1]) == 0:
                                json_State["Normal Voltage"] = True
                            if D7_D4_mask[0]&(Modbus_Value.registers[0]>>D7_D4_mask[1]) == 2:
                                json_State["Low Temp"] = True
                            if D7_D4_mask[0]&(Modbus_Value.registers[0]>>D7_D4_mask[1]) == 1:
                                json_State["Over Temp"] = True
                            if D7_D4_mask[0]&(Modbus_Value.registers[0]>>D7_D4_mask[1]) == 0:
                                json_State["Normal Temp"] = True
                            if D8_mask[0]&(Modbus_Value.registers[0]>>D8_mask[1]) == 1:
                                json_State["Battery internal resistance abnormal"] = True
                            if D15_mask[0]&(Modbus_Value.registers[0]>>D15_mask[1]) == 1:
                                json_State["Wrong identification for rated voltage"] = True

                            Modbus_Value = json.dumps(json_State)


                        elif Info['Name'] == 'Charger Status':

                            # D15-D14: Input volt status. 
                            #     00H normal
                            #     01H no power connected
                            #     02H Higher volt input
                            #     03H Input volt error.
                            # D13: Charging MOSFET is shorted.
                            # D12: Charging or Anti-reverse MOSFET is shorted.
                            # D11: Anti-reverse MOSFET is shorted.
                            # D10: Input is over current.
                            # D9: The load is Over current.
                            # D8: The load is shorted.
                            # D7: Load MOSFET is shorted.
                            # D4: PV Input is shorted.
                            # D3-2: Charging status.
                            #     00 No charging
                            #     01 Float
                            #     02 Boost
                            #     03 Equlization.
                            # D1: 0 Normal, 1 Fault.
                            # D0: 1 Running, 0 Standby


                            # Define each mask as a tuple with all the bit at 1 and distance from the right:
                            D0_mask = (0b1, 0)
                            D1_mask = (0b1, 1)
                            D3_D2_mask = (0b11, 2)
                            D4_mask = (0b1, 4)
                            D7_mask = (0b1, 7)
                            D8_mask = (0b1, 8)
                            D9_mask = (0b1, 9)
                            D10_mask = (0b1, 10)
                            D11_mask = (0b1, 11)
                            D12_mask = (0b1, 12)
                            D13_mask = (0b1, 13)
                            D15_D14_mask = (0b11, 14)

                            # Creating the json dict with all values as false
                            json_State = {}
                            json_State['Running'] = False
                            json_State['Standby'] = False
                            json_State['Normal'] = False
                            json_State['Fault'] = False
                            json_State['No charging'] = False
                            json_State['Float'] = False
                            json_State['Boost'] = False
                            json_State['Equlization'] = False
                            json_State['PV Input is shorted'] = False
                            json_State['Charging or Anti-reverse MOSFET is shorted'] = False
                            json_State['Anti-reverse MOSFET is shorted'] = False
                            json_State['Input is over current'] = False
                            json_State['The load is Over current'] = False
                            json_State['The load is shorted'] = False
                            json_State['Load MOSFET is shorted'] = False
                            json_State['Load MOSFET is shorted'] = False
                            json_State['Input voltage normal'] = False
                            json_State['No power connected'] = False
                            json_State['Higher volt input'] = False
                            json_State['Input volt error'] = False

                            # D0
                            if D0_mask[0]&(Modbus_Value.registers[0]>>D0_mask[1]) == 1:
                                json_State['Running'] = True
                            else:
                                json_State['Standby'] = True
                            # D1
                            if D1_mask[0]&(Modbus_Value.registers[0]>>D1_mask[1]) == 1:
                                json_State['Normal'] = True
                            else:
                                json_State['Fault'] = True
                            # D3-D2
                            if D3_D2_mask[0]&(Modbus_Value.registers[0]>>D3_D2_mask[1]) == 0:
                                json_State['No charging'] = True
                            if D3_D2_mask[0]&(Modbus_Value.registers[0]>>D3_D2_mask[1]) == 1:
                                json_State['Float'] = True
                            if D3_D2_mask[0]&(Modbus_Value.registers[0]>>D3_D2_mask[1]) == 2:
                                json_State['Boost'] = True
                            if D3_D2_mask[0]&(Modbus_Value.registers[0]>>D3_D2_mask[1]) == 3:
                                json_State['Equlization'] = True
                            # D4
                            if D4_mask[0]&(Modbus_Value.registers[0]>>D4_mask[1]) == 1:
                                json_State['PV Input is shorted'] = True
                            # D7
                            if D7_mask[0]&(Modbus_Value.registers[0]>>D7_mask[1]) == 1:
                                json_State['Charging or Anti-reverse MOSFET is shorted'] = True
                            # D8
                            if D8_mask[0]&(Modbus_Value.registers[0]>>D8_mask[1]) == 1:
                                json_State['Anti-reverse MOSFET is shorted'] = True
                            # D9
                            if D9_mask[0]&(Modbus_Value.registers[0]>>D9_mask[1]) == 1:
                                json_State['Input is over current'] = True
                            # D10
                            if D10_mask[0]&(Modbus_Value.registers[0]>>D10_mask[1]) == 1:
                                json_State['The load is Over current'] = True
                            # D11
                            if D11_mask[0]&(Modbus_Value.registers[0]>>D11_mask[1]) == 1:
                                json_State['The load is shorted'] = True
                            # D12
                            if D12_mask[0]&(Modbus_Value.registers[0]>>D12_mask[1]) == 1:
                                json_State['Load MOSFET is shorted'] = True
                            # D13
                            if D13_mask[0]&(Modbus_Value.registers[0]>>D13_mask[1]) == 1:
                                json_State['Load MOSFET is shorted'] = True
                            # D3-D2
                            if D15_D14_mask[0]&(Modbus_Value.registers[0]>>D15_D14_mask[1]) == 0:
                                json_State['Input voltage normal'] = True
                            if D15_D14_mask[0]&(Modbus_Value.registers[0]>>D15_D14_mask[1]) == 1:
                                json_State['No power connected'] = True
                            if D15_D14_mask[0]&(Modbus_Value.registers[0]>>D15_D14_mask[1]) == 2:
                                json_State['Higher volt input'] = True
                            if D15_D14_mask[0]&(Modbus_Value.registers[0]>>D15_D14_mask[1]) == 3:
                                json_State['Input volt error'] = True

                            Modbus_Value = json.dumps(json_State)


                        else:
                            Modbus_Value = str(float(Modbus_Value.registers[0] * Info['Multiplier']))


                        # Publish only if value changed
                        if self.Value_Dict.get(Info['Name'], None) != Modbus_Value:
                            # Save value to value dict
                            self.Value_Dict[Info['Name']] = Modbus_Value
                            Topic = Dobby_Config['System_Header'] + '/EP/' + str(self.Name) + '/' + str(Info['Name'])
                            # Publish
                            MQTT_Client.publish(Topic, payload=str(Modbus_Value), qos=0, retain=True)
                            # Log event
                            Log("Debug", "EP Logger", "MQTT Publish", "Topic: " + Topic + " - Payload: " + str(Modbus_Value))

                        time.sleep(0.05)

                    self.OK_To_Kill = True

                    time.sleep(EP_Logger.Loop_Delay)

                while self.Next_Ping > datetime.datetime.now():
                    time.sleep(EP_Logger.Loop_Delay)

                if self.Kill is True:
                    quit()



# ---------------------------------------- Init ----------------------------------------
Dobby_init()

MQTT_init()

Alert_Trigger()

Action_Trigger()

MQTT_Client_gBridge = gBridge_Trigger()

Spammer()

Log_Trigger()

Counters()

EP_Logger()

# ---------------------------------------- Loop ----------------------------------------
# Start MQTT Loop
MQTT_Client.loop_forever()
