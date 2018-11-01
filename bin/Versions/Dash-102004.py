#!/usr/bin/python

# Improvements
# Add limit slider to live graph

# Changelog
# See Changelog/Dash.txt

import dash
import dash_auth

from dash.dependencies import Input, Output, State
import dash_core_components as dcc
import dash_html_components as html
import dash_table_experiments as dt

# Neede to be able to shutdown dash
from flask import request

# MQTT
import paho.mqtt.publish as MQTT

# Time
import datetime

# MySQL
import MySQLdb

# Pandas
import pandas as pd

# Scacda
import plotly.graph_objs as go


# MISC
# import collections
# import ast

# json
# import json

# MISC
Version = 102004
# First didget = Software type 1-Production 2-Beta 3-Alpha
# Secound and third didget = Major version number
# Fourth to sixth = Minor version number


# MySQL
MySQL_Server = 'localhost'
MySQL_Username = 'dobby'
MySQL_Password = 'HereToServe'

db_pd_Connection = MySQLdb.connect(host=MySQL_Server, user=MySQL_Username, passwd=MySQL_Password)

# Dobby
MQTT_Broker = pd.read_sql("SELECT Value FROM Dobby.SystemConfig WHERE Header='MQTT' AND Target='Dobby' AND Name='Broker';", con=db_pd_Connection)
MQTT_Port = pd.read_sql("SELECT Value FROM Dobby.SystemConfig WHERE Header='MQTT' AND Target='Dobby' AND Name='Port';", con=db_pd_Connection)
MQTT_Username = pd.read_sql("SELECT Value FROM Dobby.SystemConfig WHERE Header='MQTT' AND Target='Dobby' AND Name='Username';", con=db_pd_Connection)
MQTT_Password = pd.read_sql("SELECT Value FROM Dobby.SystemConfig WHERE Header='MQTT' AND Target='Dobby' AND Name='Password';", con=db_pd_Connection)
System_Header = pd.read_sql("SELECT Value FROM Dobby.SystemConfig WHERE Header='System' AND Target='Dobby' AND Name='Header';", con=db_pd_Connection)
DashButtons_Number_Of = pd.read_sql("SELECT COUNT(id) FROM Dobby.DashButtons;", con=db_pd_Connection)

# Add users and passwords
# User auth list
db_User_List = pd.read_sql("SELECT Username, Password FROM Dobby.Users;", con=db_pd_Connection)

db_pd_Connection.close()

User_List = []

for i in db_User_List.index:
    User_List.append([db_User_List.Username[i], db_User_List.Password[i]])

del db_User_List


# Dash
app = dash.Dash()


# Dash auth
auth = dash_auth.BasicAuth(
        app,
        User_List
)

# Needed with taps
app.config['suppress_callback_exceptions'] = True


# ================================================================================ Functions ================================================================================
# ================================================================================ Functions ================================================================================
# ================================================================================ Functions ================================================================================

# ======================================== Server Shutdown ========================================
def Server_Shutdown():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


# ======================================== MQTT Publish ========================================
def MQTT_Publish(Topic, Payload):
    MQTT.single(Topic, Payload, hostname=MQTT_Broker.Value[0], port=MQTT_Port.Value[0], auth={'username': MQTT_Username.Value[0], 'password': MQTT_Password.Value[0]})


# ======================================== SQL Open /Close ========================================
def Open_db(db=""):
    try:
        db = MySQLdb.connect(host=MySQL_Server,    # your host, usually localhost
                             user=MySQL_Username,         # your username
                             passwd=MySQL_Password,  # your password
                             db=db)        # name of the data base
        return db

    except (MySQLdb.Error, MySQLdb.Warning) as e:
        print(e)
        return False


def Close_db(conn, cur):
    try:
        conn.commit()
        cur.close()
        conn.close()
        return True

    except (MySQLdb.Error, MySQLdb.Warning) as e:
        print(e)
        return False


# ======================================== SQL_To_List ========================================
def SQL_To_List(SQL_String):
    # Open db connection
    db_SQL_Connection = Open_db('')
    db_SQL_Curser = db_SQL_Connection.cursor()

    db_SQL_Curser.execute(SQL_String)
    db_List = db_SQL_Curser.fetchall()

    # Close db connection
    Close_db(db_SQL_Connection, db_SQL_Curser)

    Return_List = []

    for i in db_List:
        Return_List.append(i[0])

    return Return_List


# ======================================== SQL_Read_df ========================================
def SQL_Read_df(SQL_String):
    # Open db connection
    db_SQL_Connection = Open_db('')

    df = pd.read_sql(SQL_String, con=db_SQL_Connection)

    # Close db connection
    db_SQL_Connection.close()

    return df


# ======================================== SQL_Read ========================================
def SQL_Read(SQL_String):
    # Open db connection
    db_SQL_Connection = Open_db('')
    db_SQL_Curser = db_SQL_Connection.cursor()

    db_SQL_Curser.execute(SQL_String)
    db_Resoult = db_SQL_Curser.fetchall()

    # Close db connection
    Close_db(db_SQL_Connection, db_SQL_Curser)

    return db_Resoult


def Column_Name_Check(Column_Name):

    Name_Field_String = 'Name'

    if Column_Name == 'DeviceConfig':
        Name_Field_String = 'Hostname'
    elif Column_Name == 'Users':
        Name_Field_String = 'Username'

    return Name_Field_String


# ======================================== Generate_Device_Config_Dict ========================================
def Generate_Config_List(Config_Dropdown, Config_Dropdown_Line, db_Curser=None):

    if Config_Dropdown_Line is None or Config_Dropdown_Line == 'None':
        return [{'Setting': '', 'Value': ''}]

    Close_db_Connection = False

    if db_Curser is None:
        db_Connection = Open_db("Dobby")
        db_Curser = db_Connection.cursor()
        Close_db_Connection = True

    Name_Field_String = Column_Name_Check(Config_Dropdown)

    db_Curser.execute("SELECT `COLUMN_NAME` FROM `INFORMATION_SCHEMA`.`COLUMNS` WHERE `TABLE_SCHEMA`='Dobby' AND `TABLE_NAME`='" + Config_Dropdown.replace(" ", "_") + "';")
    Settings = db_Curser.fetchall()

    db_Curser.execute("SELECT * FROM Dobby." + Config_Dropdown.replace(" ", "_") + " WHERE `" + Name_Field_String + "`='" + Config_Dropdown_Line + "';")
    Values = db_Curser.fetchone()

    Row_List = []
    Config_Ignore_List = ['id', 'Last_Modified', 'Last_Modified']

    for i in range(len(Settings)):
        if Settings[i][0] not in Config_Ignore_List:
            Row_List.append({'Setting': [Settings[i][0]], 'Value': [Values[i]]})

    if Close_db_Connection is True:
        # Close db connection
        Close_db(db_Connection, db_Curser)

    return Row_List


# ======================================== Generate_Device_Config_Dict ========================================
def Generate_Device_Config_Dict(Selected_Device, db_Curser):

    if Selected_Device is None:
        return None

    db_Curser.execute("SELECT `COLUMN_NAME` FROM `INFORMATION_SCHEMA`.`COLUMNS` WHERE `TABLE_SCHEMA`='Dobby' AND `TABLE_NAME`='DeviceConfig';")
    Device_Config_Setting = db_Curser.fetchall()

    db_Curser.execute("SELECT * FROM Dobby.DeviceConfig WHERE Hostname='" + Selected_Device + "';")
    Device_Config_Value = db_Curser.fetchone()

    Row_List = []
    Config_Ignore_List = ['id', 'Last_Modified', 'Config_Active', 'Config_ID']

    i = 0

    for Setting in Device_Config_Setting:
        if Setting[0] not in Config_Ignore_List:
            Row_List.append({'Setting': [Setting[0]], 'Value': [Device_Config_Value[i]]})
        i = i + 1

    return Row_List


# ======================================== Generate_Variable_Dict ========================================
def Generate_Variable_Dict(String):

    Return_Dict = {}

    # Do nothing if string en empthy
    if String == "" or String is None:
        pass

    else:
        String = str(String).replace("u'", "'")

        for i in String.split('<*>'):
            # Skip if line is ''
            if i == '':
                continue

            Dict_Entry = i.split('<;>')

            # I asume that 2 x - and 2  : = datetime
            if Dict_Entry[1].count('-') == 2 and Dict_Entry[1].count(':') == 2:
                # If 7th last char is . then the datetime has ms in it, it needs to be removed
                if Dict_Entry[1][19:-6] == ".":
                    Dict_Entry[1] = datetime.datetime.strptime(Dict_Entry[1][:-7], '%Y-%m-%d %H:%M:%S')
                else:
                    Dict_Entry[1] = datetime.datetime.strptime(Dict_Entry[1], '%Y-%m-%d %H:%M:%S')

            elif "[" and "]" in Dict_Entry[1]:
                # Remove "'"
                Dict_Entry[1] = Dict_Entry[1].replace("'", "")
                # Remove brackets
                Dict_Entry[1] = Dict_Entry[1].replace("[", "")
                Dict_Entry[1] = Dict_Entry[1].replace("]", "")
                # Convert to list
                Dict_Entry[1] = Dict_Entry[1].split(', ')

            Return_Dict[Dict_Entry[0]] = Dict_Entry[1]

    return Return_Dict


# ======================================== Generate_Variable_Dict ========================================
def Generate_Variable_String(Dict):

    Return_String = ''

    for Key, Value in Dict.iteritems():
        Return_String = Return_String + str(Key) + '<;>' + str(Value) + '<*>'

    return Return_String


def Tabs_List():

    Tabs_List = []

    Tabs_List.append(dcc.Tab(label='Config', value='Config_Tab'))

    # Tabs_List.append(dcc.Tab(label='Devices', value='Config_Tab'))

    Tabs_List.append(dcc.Tab(label='Log Trigger', value='Log_Trigger_Tab'))

    Tabs_List.append(dcc.Tab(label='System', value='System_Tab'))

    return Tabs_List


def Config_Tab_Dropdown_List():

    return ['DashButtons', 'DeviceConfig', 'Log Trigger', 'Mail Trigger', 'Spammer', 'Users']


# ======================================== Layout ========================================
app.layout = html.Div([


    dcc.Tabs(id="tabs", value='Config_Tab', children=Tabs_List()),

    html.Div(id='Main_Tabs'),

    # No idea why this needs to be here, if its not the tabs with datatables does not load
    html.Div([
        dt.DataTable(rows=[{}]),
        ], style={"display": "none"}),

    # Places to store variables
    html.Div([
        html.Div(id='Config_Tab_Variables', children=""),
        # html.Div(id='Device_Tab_Variables', children=""),
        html.Div(id='Log_Trigger_Tab_Variables', children=""),
        # html.Div(id='Log_Trigger_Config_Tab_Variables', children=""),
        html.Div(id='System_Tab_Variables', children=""),

        ], style={'display': 'none'})
    ])


# ======================================== Tabs ========================================
@app.callback(
    Output('Main_Tabs', 'children'),
    [
        Input('tabs', 'value'),
        ],
    [
        State('Config_Tab_Variables', 'children'),
        # State('Device_Tab_Variables', 'children'),
        State('Log_Trigger_Tab_Variables', 'children'),
        # State('Log_Trigger_Config_Tab_Variables', 'children'),
        State('System_Tab_Variables', 'children'),
        ]
    )
def render_content(tab, Config_Tab_Variables, Log_Trigger_Tab_Variables, System_Tab_Variables):
    # ======================================== Config Tab ========================================
    # ======================================== Config Tab ========================================
    # ======================================== Config Tab ========================================
    if tab == 'Config_Tab':
        Config_Tab_Variables = Generate_Variable_Dict(Config_Tab_Variables)

        return html.Div(
            id='Config_Tab',
            children=[
                # Dropdown to select What to configure
                dcc.Dropdown(
                    id='Config_Dropdown',
                    options=[{'label': Config_Option, 'value': Config_Option} for Config_Option in Config_Tab_Dropdown_List()],
                    value=Config_Tab_Variables.get('Config_Dropdown', None),
                    ),
                # Dropdown to select What LINE to configure
                dcc.Dropdown(
                    id='Config_Dropdown_Line',
                    options=[],
                    value=Config_Tab_Variables.get('Config_Dropdown_Line', None),
                    ),
                # Config table
                dt.DataTable(
                    id='Config_Table',
                    rows=[],
                    columns=['Setting', 'Value'],
                    min_height='72vh',
                    resizable=True,
                    editable=True,
                    filterable=True,
                    sortable=True,
                    ),
                html.Button('Read', id='Config_Read', n_clicks=int(Config_Tab_Variables.get('Config_Read', 0)), style={'margin-top': '5px'}),
                html.Button('Save', id='Config_Save', n_clicks=int(Config_Tab_Variables.get('Config_Save', 0)), style={'margin-left': '5px', 'margin-top': '5px'}),
                ],
            ),

    # ======================================== Log Trigger Tab ========================================
    # ======================================== Log Trigger Tab ========================================
    # ======================================== Log Trigger Tab ========================================
    elif tab == 'Log_Trigger_Tab':

        Log_Trigger_Tab_Variables = Generate_Variable_Dict(Log_Trigger_Tab_Variables)

        return html.Div(
            id='Log_Trigger_Tab',
            children=[
                # Dropdown to select logs
                dcc.Dropdown(
                    id='Log_Trigger_Dropdown',
                    options=[{'label': Trigger, 'value': Trigger} for Trigger in SQL_To_List("SELECT DISTINCT Name FROM DobbyLog.Log_Trigger;")],
                    multi=True,
                    value=Log_Trigger_Tab_Variables.get('Log_Trigger_Dropdown', None),
                ),

                dcc.Graph(
                    id='Log_Trigger_Graph',
                    style={
                        'height': '70vh',
                        'width': '95vw',
                        'padding': 5,
                        }
                    ),

                html.Div(
                    id='Log_Trigger_Tab',
                    style={
                        'width': '90vw',
                        'padding': 50,
                        'display': 'inline-block'
                        },
                    children=[
                        dcc.RangeSlider(
                            id='Log_Trigger_Slider',
                            min=0,
                            max=100,
                            step=1,
                            value=[95, 100],
                            allowCross=False,
                            marks={},
                        ),
                    ],
                ),
            ],
        )

    # ======================================== System Tab ========================================
    # ======================================== System Tab ========================================
    # ======================================== System Tab ========================================
    elif tab == 'System_Tab':
        System_Tab_Variables = Generate_Variable_Dict(System_Tab_Variables)

        return html.Div([
            html.Button('Check for updates', id='System_Update_Button', n_clicks=0, style={'margin-top': '5px'}),
            html.Button('Quit', id='System_Quit_Button', n_clicks=0, style={'margin-left': '5px', 'margin-top': '5px'}),
        ], id='System_Tab')


# ================================================================================ Callbacks ================================================================================
# ================================================================================ Callbacks ================================================================================
# ================================================================================ Callbacks ================================================================================
# ================================================================================ Callbacks ================================================================================

# ======================================== Config Tab - Callbacks ========================================
# Device_Config_Tab_Variables
@app.callback(
    Output('Config_Tab_Variables', 'children'),
    [
        Input('Config_Dropdown', 'value'),
        Input('Config_Dropdown_Line', 'value'),
        Input('Config_Read', 'n_clicks'),
        Input('Config_Save', 'n_clicks'),
        ],
    [
        State('Config_Table', 'rows'),
        State('Config_Tab_Variables', 'children'),
        ]
    )
def Config_Tab_Variables(Config_Dropdown, Config_Dropdown_Line, Config_Read, Config_Save, Config_Table, Config_Tab_Variables):

    Config_Tab_Variables = Generate_Variable_Dict(Config_Tab_Variables)

    # Dropdowns
    Config_Tab_Variables['Config_Dropdown'] = Config_Dropdown
    if Config_Dropdown is None:
        Config_Tab_Variables['Config_Dropdown'] = "None"
        Config_Tab_Variables['Config_Dropdown_Line'] = "None"
    else:
        if Config_Dropdown_Line is None:
            Config_Tab_Variables['Config_Dropdown_Line'] = "None"
        else:
            Config_Tab_Variables['Config_Dropdown_Line'] = Config_Dropdown_Line

    # # Button
    if int(Config_Tab_Variables.get('Config_Save', 0)) != int(Config_Save):
        if Config_Tab_Variables['Config_Dropdown_Line'] != "None":
            db_Connection = Open_db("Dobby")
            db_Curser = db_Connection.cursor()

            Current_Config = Generate_Config_List(Config_Dropdown, Config_Dropdown_Line, db_Curser)

            # Needed to refer between tables
            i = 0

            # Needed so you dont change the config id when no changes is made
            Config_Changes = {}

            for Current_Config_Row in Current_Config:

                # If value is '' set it to NULL
                if Config_Table[i]['Value'] == '':
                    Config_Changes[Config_Table[i]['Setting'][0]] = 'NULL'

                elif Config_Table[i]['Value'][0] != Current_Config_Row['Value'][0]:
                    # Add chnages to chnages dict
                    Config_Changes[Config_Table[i]['Setting'][0]] = Config_Table[i]['Value']

                i = i + 1

            if Config_Changes != {}:
                Name_Field_String = Column_Name_Check(Config_Dropdown)

                # Get device id for use in sql changes below
                db_Curser.execute("SELECT id FROM `Dobby`.`" + Config_Dropdown.replace(" ", "_") + "` WHERE `" + Name_Field_String + "`='" + str(Config_Dropdown_Line) + "';")
                Row_id = db_Curser.fetchone()
                Row_id = str(Row_id[0])

                # Apply changes
                for key, value in Config_Changes.iteritems():
                    if value is 'NULL':
                        db_Curser.execute("UPDATE `Dobby`.`" + Config_Dropdown.replace(" ", "_") + "` SET `" + str(key) + "`=NULL WHERE `id`='" + Row_id + "';")
                    else:
                        db_Curser.execute("UPDATE `Dobby`.`" + Config_Dropdown.replace(" ", "_") + "` SET `" + str(key) + "`='" + str(value) + "' WHERE `id`='" + Row_id + "';")

                # Update Last modified
                db_Curser.execute("UPDATE `Dobby`.`" + Config_Dropdown.replace(" ", "_") + "` SET `Last_Modified`='" + str(datetime.datetime.now()) + "' WHERE `id`='" + Row_id + "';")

                if Config_Dropdown == "DeviceConfig":
                    # Get Current Config_ID
                    db_Curser.execute("SELECT Config_ID FROM `Dobby`.`" + Config_Dropdown.replace(" ", "_") + "` WHERE `id`='" + Row_id + "';")
                    Current_Config_ID = db_Curser.fetchone()

                    # Update Config_ID
                    db_Curser.execute("UPDATE `Dobby`.`" + Config_Dropdown.replace(" ", "_") + "` SET `Config_ID`='" + str(Current_Config_ID[0] + 1) + "' WHERE `id`='" + Row_id + "';")

            # Close db connection
            Close_db(db_Connection, db_Curser)

    Config_Tab_Variables['Config_Read'] = Config_Read
    Config_Tab_Variables['Config_Save'] = Config_Save

    return Generate_Variable_String(Config_Tab_Variables)


# ======================================== Device Config Tab - Callbacks ========================================
@app.callback(
    Output('Config_Dropdown_Line', 'options'),
    [
        Input('Config_Dropdown', 'value'),
        ],
    [
        State('Config_Tab_Variables', 'children'),
        ],
    )
def Config_Tab_Line_Dropdown(Config_Dropdown, Config_Tab_Variables):

    Config_Tab_Variables = Generate_Variable_Dict(Config_Tab_Variables)

    if Config_Dropdown is None or Config_Dropdown == 'None':
        return {'label': '', 'value': ''}

    Name_Field_String = Column_Name_Check(Config_Dropdown)

    db_Connection = Open_db("Dobby")
    db_Curser = db_Connection.cursor()

    db_Curser.execute("SELECT id, `" + Name_Field_String + "` FROM `Dobby`.`" + Config_Dropdown.replace(" ", "_") + "` ORDER BY `" + Name_Field_String + "`;")
    db_Fetch = db_Curser.fetchall()

    # Close db connection
    Close_db(db_Connection, db_Curser)

    Return_List = []

    for Key, Value in db_Fetch:
        Return_List.append({'label': Value, 'value': Value})

    return Return_List


@app.callback(
    Output('Config_Table', 'rows'),
    [
        Input('Config_Dropdown_Line', 'value'),
        Input('Config_Read', 'n_clicks'),
        ],
    [
        State('Config_Dropdown', 'value'),
        ],
    )
def Config_Tab_Table(Config_Dropdown_Line, Config_Read, Config_Dropdown):

    return Generate_Config_List(Config_Dropdown, Config_Dropdown_Line)


# ======================================== Device Config Tab - Callbacks ========================================
# Device_Config_Tab_Variables
@app.callback(
    Output('Device_Config_Tab_Variables', 'children'),
    [
        Input('Device_Config_Dropdown', 'value'),
        Input('Device_Config_Dropdown', 'value'),
        Input('Device_Config_Read', 'n_clicks'),
        Input('Device_Config_Save', 'n_clicks'),
        Input('Device_Config_Send', 'n_clicks'),
        Input('Device_Config_Reboot', 'n_clicks'),
        Input('Device_Config_Shutdown', 'n_clicks'),
        ],
    [
        State('Device_Config_Tab_Variables', 'children')
        ]
    )
def Device_Config_Tab_Variables(Device_Config_Dropdown, Device_Config_Read, Device_Config_Save, Device_Config_Send, Device_Config_Reboot, Device_Config_Shutdown, Device_Config_Tab_Variables):

    Device_Config_Tab_Variables = Generate_Variable_Dict(Device_Config_Tab_Variables)

    Device_Config_Tab_Variables['Device_Config_Dropdown'] = Device_Config_Dropdown

    Button_List = [Device_Config_Read, Device_Config_Save, Device_Config_Send, Device_Config_Reboot, Device_Config_Shutdown]
    Button_List_Text = ['Device_Config_Read', 'Device_Config_Save', 'Device_Config_Send', 'Device_Config_Reboot', 'Device_Config_Shutdown']

    # Check if buttons was presses
    for i in range(len(Button_List)):
        if Button_List[i] != int(Device_Config_Tab_Variables.get(Button_List_Text[i], 0)):
            Device_Config_Tab_Variables['Last_Click'] = Button_List_Text[i]

            # Shutdown / Reboot
            if Device_Config_Tab_Variables['Device_Config_Dropdown'] is not None or []:
                Action = None
                if Device_Config_Tab_Variables.get('Last_Click', None) == "Device_Config_Reboot":
                    if Device_Config_Tab_Variables.get('Device_Config_Reboot', 0) != Device_Config_Reboot:
                        Action = 'Reboot'
                elif Device_Config_Tab_Variables.get('Last_Click', None) == "Device_Config_Shutdown":
                    if Device_Config_Tab_Variables.get('Device_Config_Shutdown', 0) != Device_Config_Shutdown:
                        Action = 'Shutdown'
                if Action is not None:
                    # Set Last_Click to none to prevent repress when changing back to tab
                    Device_Config_Tab_Variables['Last_Click'] = None
                    MQTT.single(System_Header.Value[0] + "/Commands/" + str(Device_Config_Tab_Variables['Device_Config_Dropdown']) + "/Power", Action + ";", hostname=MQTT_Broker.Value[0], port=MQTT_Port.Value[0], auth={'username': MQTT_Username.Value[0], 'password': MQTT_Password.Value[0]})

            Device_Config_Tab_Variables[Button_List_Text[i]] = Button_List[i]
            break

    return Generate_Variable_String(Device_Config_Tab_Variables)


# Update Device Config rows
@app.callback(
    Output('Device_Config_Table', 'rows'),
    [
        Input('Device_Config_Tab_Variables', 'children'),
        Input('Device_Config_Save', 'n_clicks'),
        ],
    [
        State('Device_Config_Table', 'rows'),
        ]
    )
def Device_Config_Tab_Config_Show(Device_Config_Tab_Variables, Device_Config_Save, Device_Config_Table):

    # Open db connection
    db_Write_Connection = Open_db('Dobby')
    db_Write_Curser = db_Write_Connection.cursor()

    # Import variables from div able
    Device_Config_Tab_Variables = Generate_Variable_Dict(Device_Config_Tab_Variables)

    # Do nothing if no device have been selected in the dropdown
    if Device_Config_Tab_Variables['Device_Config_Dropdown'] == "None":
        Close_db(db_Write_Connection, db_Write_Curser)
        return [{'Setting': '', 'Value': ''}]

    # ======================================== Save Config ========================================
    elif Device_Config_Tab_Variables.get('Last_Click', "None") == "Device_Config_Save":
        Current_Config = Generate_Device_Config_Dict(Device_Config_Tab_Variables['Device_Config_Dropdown'], db_Write_Curser)

        # Needed to refer between tables
        i = 0

        # Needed so you dont change the config id when no changes is made
        Config_Changes = {}

        for Current_Config_Row in Current_Config:

            # If value is '' set it to NULL
            if Device_Config_Table[i]['Value'] == '':
                Config_Changes[Device_Config_Table[i]['Setting'][0]] = 'NULL'

            elif Device_Config_Table[i]['Value'][0] != Current_Config_Row['Value'][0]:
                # Add chnages to chnages dict
                Config_Changes[Device_Config_Table[i]['Setting'][0]] = Device_Config_Table[i]['Value']

            i = i + 1

        if Config_Changes != {}:
            # Get device id for use in sql changes below
            db_Write_Curser.execute("SELECT id FROM Dobby.DeviceConfig WHERE Hostname='" + Device_Config_Tab_Variables['Device_Config_Dropdown'] + "';")
            Device_id = db_Write_Curser.fetchone()
            Device_id = str(Device_id[0])

            # Apply changes
            for key, value in Config_Changes.iteritems():
                if value is 'NULL':
                    db_Write_Curser.execute("UPDATE `Dobby`.`DeviceConfig` SET `" + str(key) + "`=NULL WHERE `id`='" + Device_id + "';")
                else:
                    db_Write_Curser.execute("UPDATE `Dobby`.`DeviceConfig` SET `" + str(key) + "`='" + str(value) + "' WHERE `id`='" + Device_id + "';")

            # Get Current Config_ID
            db_Write_Curser.execute("SELECT Config_ID FROM Dobby.DeviceConfig WHERE `id`='" + Device_id + "';")
            Current_Config_ID = db_Write_Curser.fetchone()

            # Update Config_ID
            db_Write_Curser.execute("UPDATE `Dobby`.`DeviceConfig` SET `Config_ID`='" + str(Current_Config_ID[0] + 1) + "' WHERE `id`='" + Device_id + "';")

            # Update Last modified
            db_Write_Curser.execute("UPDATE `Dobby`.`DeviceConfig` SET `Last_Modified`='" + str(datetime.datetime.now()) + "' WHERE `id`='" + Device_id + "';")

            Device_Config_Tab_Variables['Last_Click'] = None

    # ======================================== Send Config ========================================
    elif Device_Config_Tab_Variables.get('Last_Click', "None") == "Device_Config_Send":
        Device_Config_Tab_Variables['Last_Click'] = None
        MQTT.single(System_Header.Value[0] + "/Commands/Dobby/Config", Device_Config_Tab_Variables['Device_Config_Dropdown'] + ",-1;", hostname=MQTT_Broker.Value[0], port=MQTT_Port.Value[0], auth={'username': MQTT_Username.Value[0], 'password': MQTT_Password.Value[0]})

    # ======================================== Return table ========================================
    Return_Dict = Generate_Device_Config_Dict(Device_Config_Tab_Variables['Device_Config_Dropdown'], db_Write_Curser)

    Close_db(db_Write_Connection, db_Write_Curser)

    return Return_Dict


# ======================================== Log Trigger Tab - Callbacks ========================================
# Log_Trigger_Tab_Variables
@app.callback(
    Output('Log_Trigger_Tab_Variables', 'children'),
    [
        Input('Log_Trigger_Dropdown', 'value'),
        Input('Log_Trigger_Slider', 'value'),
        ],
    [
        State('Log_Trigger_Tab_Variables', 'children')
        ]
    )
def Log_Trigger_Tab_Variables(Log_Trigger_Dropdown, Log_Trigger_Slider, Log_Trigger_Tab_Variables):

    Log_Trigger_Tab_Variables = Generate_Variable_Dict(Log_Trigger_Tab_Variables)

    Log_Trigger_Tab_Variables['Log_Trigger_Dropdown'] = Log_Trigger_Dropdown

    # Slider
    if Log_Trigger_Dropdown is not None and Log_Trigger_Dropdown != []:

        Slider_Name_String = ""
        i = 0
        # Find first entry
        for Selection in Log_Trigger_Dropdown:
            if i != 0:
                Slider_Name_String = Slider_Name_String + " OR "
            Slider_Name_String = Slider_Name_String + "`Name`='" + str(Selection) + "'"
            i = i + 1

        db_Connection = Open_db("DobbyLog")
        db_Curser = db_Connection.cursor()

        db_Curser.execute("SELECT DateTime FROM DobbyLog.Log_Trigger WHERE " + Slider_Name_String + " ORDER BY id ASC LIMIT 1;")
        Min_Date = db_Curser.fetchone()

        db_Curser.execute("SELECT DateTime FROM DobbyLog.Log_Trigger WHERE " + Slider_Name_String + " ORDER BY id DESC LIMIT 1;")
        Max_Date = db_Curser.fetchone()

        # Close db connection
        Close_db(db_Connection, db_Curser)

        if Min_Date is not None or Max_Date is not None:
            Min_Date = Min_Date[0]
            Max_Date = Max_Date[0]

            # Save min/max
            Log_Trigger_Tab_Variables['Slider_Min_Date'] = Min_Date
            Log_Trigger_Tab_Variables['Slider_Max_Date'] = Max_Date

            Time_Span = Max_Date - Min_Date
            Time_Jumps = Time_Span / 100

            # Save Low value
            if Log_Trigger_Slider[0] == 0:
                Log_Trigger_Tab_Variables['Slider_Value_Low'] = Min_Date
            elif Log_Trigger_Slider[0] == 100:
                Log_Trigger_Tab_Variables['Slider_Value_Low'] = Max_Date
            else:
                Log_Trigger_Tab_Variables['Slider_Value_Low'] = Min_Date + Time_Jumps * Log_Trigger_Slider[0]

            # removes ".######" from the datetime string
            if len(str(Log_Trigger_Tab_Variables['Slider_Value_Low'])) > 19:
                Log_Trigger_Tab_Variables['Slider_Value_Low'] = str(Log_Trigger_Tab_Variables['Slider_Value_Low'])[:-7]

            # Save high value
            if Log_Trigger_Slider[1] == 0:
                Log_Trigger_Tab_Variables['Slider_Value_High'] = Min_Date
            elif Log_Trigger_Slider[1] == 100:
                Log_Trigger_Tab_Variables['Slider_Value_High'] = Max_Date
            else:
                Log_Trigger_Tab_Variables['Slider_Value_High'] = Min_Date + Time_Jumps * Log_Trigger_Slider[1]

            # removes ".######" from the datetime string
            if len(str(Log_Trigger_Tab_Variables['Slider_Value_High'])) > 19:
                Log_Trigger_Tab_Variables['Slider_Value_High'] = str(Log_Trigger_Tab_Variables['Slider_Value_High'])[:-7]

    return Generate_Variable_String(Log_Trigger_Tab_Variables)


# ======================================== Log_Trigger - Slider Marks ========================================
@app.callback(
    Output('Log_Trigger_Slider', 'marks'),
    [
        Input('Log_Trigger_Tab_Variables', 'children')
        ],
    [
        # State('Log_Trigger_Tab_Variables', 'children'),
        ]
    )
def Log_Trigger_Update_Slider_Marks(Log_Trigger_Tab_Variables):

    Log_Trigger_Tab_Variables = Generate_Variable_Dict(Log_Trigger_Tab_Variables)

    if Log_Trigger_Tab_Variables.get('Log_Trigger_Dropdown', 'None') == 'None':
        return {}

    Time_Span = Log_Trigger_Tab_Variables['Slider_Max_Date'] - Log_Trigger_Tab_Variables['Slider_Min_Date']
    Time_Jumps = Time_Span / 10

    Marks_Dict = {}

    # Add the first and last label
    Marks_Dict['0'] = {'label': Log_Trigger_Tab_Variables['Slider_Min_Date']}
    Marks_Dict['100'] = {'label': Log_Trigger_Tab_Variables['Slider_Max_Date']}

    print "Log_Trigger_Tab_Variables"
    print Log_Trigger_Tab_Variables

    # Add the rest of the labels
    for i in range(1, 10):
        Name = str(i * 10)
        Label = str(Log_Trigger_Tab_Variables['Slider_Min_Date'] + Time_Jumps * i)

        # The [:-7] removes the ms from the end of the string
        if "." in Label:
            Label = Label[:-7]

        Marks_Dict[Name] = {'label': Label}

    return Marks_Dict


# Update Graph
@app.callback(
    Output('Log_Trigger_Graph', 'figure'),
    [
        Input('Log_Trigger_Tab_Variables', 'children'),
        ],
    )
def Log_Trigger_Graph(Log_Trigger_Tab_Variables):

    # Import variables from div able
    Log_Trigger_Tab_Variables = Generate_Variable_Dict(Log_Trigger_Tab_Variables)

    # Do nothing if no device have been selected in the dropdown
    if Log_Trigger_Tab_Variables['Log_Trigger_Dropdown'] == 'None' or Log_Trigger_Tab_Variables is {}:
        return {'data': ''}

    # ======================================== Read Logs ========================================
    else:
        db_Connection = Open_db("DobbyLog")
        db_Curser = db_Connection.cursor()

        Data = []

        for Name in Log_Trigger_Tab_Variables['Log_Trigger_Dropdown']:

            json_Tag_List = SQL_To_List("SELECT DISTINCT json_Tag FROM DobbyLog.Log_Trigger WHERE Name='" + str(Name) + "' AND datetime>'" + str(Log_Trigger_Tab_Variables['Slider_Value_Low']) + "' ORDER BY json_Tag;")

            if len(json_Tag_List) > 1:
                # Create and style traces
                for Tag_Name in json_Tag_List:

                    if "Min" in Tag_Name:
                        Data.append(
                            go.Scatter(
                                x=SQL_To_List("SELECT DateTime FROM DobbyLog.Log_Trigger WHERE Name='" + str(Name) + "' AND json_Tag='" + str(Tag_Name) + "' AND datetime>'" + str(Log_Trigger_Tab_Variables['Slider_Value_Low']) + "' ORDER BY id DESC;"),
                                y=SQL_To_List("SELECT Value FROM DobbyLog.Log_Trigger WHERE Name='" + str(Name) + "' AND json_Tag='" + str(Tag_Name) + "' AND datetime>'" + str(Log_Trigger_Tab_Variables['Slider_Value_Low']) + "' ORDER BY id DESC;"),
                                name=str(Name + " - " + Tag_Name),
                                mode='lines+markers',
                                line=dict(
                                    dash='dash',
                                )
                            )
                        )

                    elif "Max" in Tag_Name:
                        Data.append(
                            go.Scatter(
                                x=SQL_To_List("SELECT DateTime FROM DobbyLog.Log_Trigger WHERE Name='" + str(Name) + "' AND json_Tag='" + str(Tag_Name) + "' AND datetime>'" + str(Log_Trigger_Tab_Variables['Slider_Value_Low']) + "' ORDER BY id DESC;"),
                                y=SQL_To_List("SELECT Value FROM DobbyLog.Log_Trigger WHERE Name='" + str(Name) + "' AND json_Tag='" + str(Tag_Name) + "' AND datetime>'" + str(Log_Trigger_Tab_Variables['Slider_Value_Low']) + "' ORDER BY id DESC;"),
                                name=str(Name + " - " + Tag_Name),
                                mode='lines+markers',
                                line=dict(
                                    dash='dot',
                                )
                            )
                        )

                    elif "Current" in Tag_Name:
                        Data.append(
                            go.Scatter(
                                x=SQL_To_List("SELECT DateTime FROM DobbyLog.Log_Trigger WHERE Name='" + str(Name) + "' AND json_Tag='" + str(Tag_Name) + "' AND datetime>'" + str(Log_Trigger_Tab_Variables['Slider_Value_Low']) + "' ORDER BY id DESC;"),
                                y=SQL_To_List("SELECT Value FROM DobbyLog.Log_Trigger WHERE Name='" + str(Name) + "' AND json_Tag='" + str(Tag_Name) + "' AND datetime>'" + str(Log_Trigger_Tab_Variables['Slider_Value_Low']) + "' ORDER BY id DESC;"),
                                name=str(Name + " - " + Tag_Name),
                                mode='lines+markers',
                            )
                        )

                    else:
                        Data.append(
                            go.Scatter(
                                x=SQL_To_List("SELECT DateTime FROM DobbyLog.Log_Trigger WHERE Name='" + str(Name) + "' AND json_Tag='" + str(Tag_Name) + "' AND datetime>'" + str(Log_Trigger_Tab_Variables['Slider_Value_Low']) + "' ORDER BY id DESC;"),
                                y=SQL_To_List("SELECT Value FROM DobbyLog.Log_Trigger WHERE Name='" + str(Name) + "' AND json_Tag='" + str(Tag_Name) + "' AND datetime>'" + str(Log_Trigger_Tab_Variables['Slider_Value_Low']) + "' ORDER BY id DESC;"),
                                name=str(Name + " - " + Tag_Name),
                                mode='lines+markers',
                            )
                        )
            else:
                # Create and style traces
                Data.append(
                    go.Scatter(
                        x=SQL_To_List("SELECT DateTime FROM DobbyLog.Log_Trigger WHERE Name='" + str(Name) + "' AND datetime>'" + str(Log_Trigger_Tab_Variables['Slider_Value_Low']) + "' ORDER BY id DESC;"),
                        y=SQL_To_List("SELECT Value FROM DobbyLog.Log_Trigger WHERE Name='" + str(Name) + "' AND datetime>'" + str(Log_Trigger_Tab_Variables['Slider_Value_Low']) + "' ORDER BY id DESC;"),
                        name=str(Name),
                        mode='lines+markers',
                    )
                )
        Close_db(db_Connection, db_Curser)

        # Edit the layout
        layout = dict(
            # title = 'Average High and Low Temperatures in New York',
            # xaxis=dict(title='Timestamp'),
            # yaxis = dict(title = 'Temperature (degrees F)'),
        )

        fig = dict(data=Data, layout=layout)

        return fig


# ======================================== System Tab - Callbacks ========================================
# Button Tabs
@app.callback(
    Output('System_Tab_Variables', 'children'),
    [
        Input('System_Quit_Button', 'n_clicks'),
        Input('System_Update_Button', 'n_clicks'),
        ],
    [
        State('System_Tab_Variables', 'children'),
        ],
    )
def System_Tab_Buttons(System_Quit_Button, System_Update_Button, System_Tab_Variables):

    # Import variables from div able
    System_Tab_Variables = Generate_Variable_Dict(System_Tab_Variables)

    if int(System_Tab_Variables.get('System_Update_Button', 0)) != int(System_Update_Button):
        System_Tab_Variables['System_Update_Button'] = System_Update_Button

        print "working here"

    elif int(System_Tab_Variables.get('System_Quit_Button', 0)) != int(System_Quit_Button):
        System_Tab_Variables['System_Quit_Button'] = System_Quit_Button

        print "System shutdown requested, shutting down"
        Server_Shutdown()

    return Generate_Variable_String(System_Tab_Variables)


# FIX - Move css to local storage
app.css.append_css({"external_url": "https://codepen.io/chriddyp/pen/bWLwgP.css"})
# Removed undo/redo
app.css.append_css({'external_url': 'http://rawgit.com/lwileczek/Dash/master/undo_redo5.css'})


if __name__ == '__main__':
    app.run_server(debug=True,  host='0.0.0.0')
