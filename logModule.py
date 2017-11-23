#!/usr/bin/python
import logging

class Logs(object):
    # Function to display script logs and save it in the log file

    def __init__(self,logfile):
        self.logfile = logfile
        #1.Create logger instance
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        #2.Create file handler to save test logs to file.
        log_fh = logging.FileHandler(self.logfile,mode='w')
        log_fh.setLevel(logging.DEBUG)
        #3.Create console handler to ouput logs to Console as well.
        log_ch = logging.StreamHandler()
        log_ch.setLevel(logging.DEBUG)
        #4.Create log formatter string
        #formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)8s - %(message)s')
        formatter = logging.Formatter('%(asctime)s - %(threadName)10s - %(levelname)8s - %(message)s')
        log_fh.setFormatter(formatter)
        log_ch.setFormatter(formatter)
        #5.Add 4 to handlers
        self.logger.addHandler(log_fh)
        self.logger.addHandler(log_ch)

    def runTest(self):
        self.logger.info("Collect info logs")
        self.logger.debug("collect debug logs")
        self.logger.error("collect error logs")

if __name__ == '__main__':
    temp_file = "abc_logs.txt"
    obj = Logs(temp_file)
    #obj.collect_logs()
    obj.runTest()
