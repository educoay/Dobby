import utime


class Init:

    # -------------------------------------------------------------------------------------------------------
    def __init__(self, Dobby):
        # Referance to dobby
        self.Dobby = Dobby
        self.Dobby.Log(1, "Timer", "Initializing")
        # Var to hold configured Timeres
        self.Timers = {}
        # Log Event
        self.Dobby.Log(0, "Timer", "Initialization complete")


    def Loop(self):
        # Run loop for all Timers
        for Name in self.Timers:
            # Run loop
            self.Timers[Name].Loop()


    def Add(self, Name, Timeout_ms, Callback, Argument=None, Logging=True):
        # Create Timer
        self.Timers[Name] = self.New_Timer(self.Dobby, Name, Timeout_ms, Callback, Argument, Logging)
        # Return timer so we can use the as refferance in the other end
        return self.Timers[Name]


    class New_Timer:

        # Custom Exception
        class Timer_Error(Exception):
            pass


        # -------------------------------------------------------------------------------------------------------
        def __init__(self, Dobby, Name, Timeout_ms, Callback, Argument, Logging):
            # Referance to dobby
            self.Dobby = Dobby
            # Log event
            self.Dobby.Log(0, "Timer-" + str(Name), "Initializing")

            # Store name
            self.Name = Name
            # Store logging
            self.Logging = Logging
            # How long before triggering the command
            self.Timeout_ms = Timeout_ms
            # This var is the one we use diff() on and then check agains Timeout_ms
            # if larger then timeout ms then trigger action
            self.Start_ms = None
        
            # If set to True, this class instance will be deleted during next run of Timer.Loop()
            self.Delete = False
            # Indicated if we currently have a timer active

            # What function the timer is going to trigger
            self.Callback = Callback
            # Argument to trigger with command
            self.Argument = Argument
            # How many times we need to run the Timer
            self.Count = 0

            # State of the timer:
            # True = Running
            # False = Ideling / Waiting for reset
            self.Running = False


        def Loop(self):
            # Check if we are running
            if self.Running == False:
                return

            # check if we need to wait
            elif utime.ticks_diff(utime.ticks_ms(), self.Start_ms) < self.Timeout_ms:
                return

            # Trigger Callback
            else:
                # check if we ran all count's of the timer
                if self.Count <= 0:
                    # Stop so we dont start again before told to do so
                    self.Stop()
                # Trigger the timer and remove one from count
                else:
                    self.Count = self.Count - 1
                    if self.Logging == True:
                        # Log event
                        self.Dobby.Log(0, "Timer", "Triggering callback: " + self.Name)
                    if self.Argument != None:
                        # Trigger the callback with argument
                        try:
                            self.Callback(self.Argument)
                        except TypeError as e:
                            raise self.Timer_Error("Error: " + str(e) + " Name:" + str(self.Name) + " Timeout_ms:" + str(self.Timeout_ms) + " Callback:" + str(self.Callback) + " Argument:" + str(self.Argument))

                    else:
                        # Trigger the callback without arguemtn
                        self.Callback()


        def Start(self, Argument=None, Count=None, Timeout_ms=None, Callback=None):
            # If Argument is "" set to none aka clear
            if Argument == "":
                self.Argument = None
            # Set Argument if not None
            elif Argument != None:
                self.Argument = Argument
            # Set Count if not None
            if Count != None:
                self.Count = Count
            # Set Callback if not None
            if Callback != None:
                self.Callback = Callback
            # Set Timeout_ms if not None
            if Timeout_ms != None:
                self.Timeout_ms = Timeout_ms
            # Set Count to 1 if 0 so we run the Timer
            if self.Count == 0:
                self.Count = 1
            # Starts or resets the timer
            self.Running = True
            # Note or reset start time
            self.Start_ms = utime.ticks_ms()


        def Stop(self, Delete=False):
            # Do nothing if already stopped
            if self.Running == False:
                return 
            # Stopps the timer if active
            self.Running = False
            # Check if we need to mark the timer for deleation in next Timer.Loop
            if Delete == True:
                self.Delete = True