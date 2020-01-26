#!/usr/bin/python
import os,sys,time, shutil
import glob
import subprocess as sp
import argparse
import re
import threading
import glob
import pdb
import logging


class Youtubedl(object):
    """Using youtube-dl to download the audio and video of the given link
    """
    def __init__(self,link):

        #Store youtube links in a list
        self.links = link.split(',')

        #Project Youtube Folders and Log file
        self.parentFolder = r"/home/neo/youtube/"
        self.youtubeDownloadFolder = "{}downloads/".format(self.parentFolder)
        self.youtubeAudioFolder = "{}audio".format(self.youtubeDownloadFolder)
        self.youtubeVideoFolder = "{}video".format(self.youtubeDownloadFolder)
        self.youtubeLogsFolder = "{}logs/".format(self.parentFolder)
        self.youtubeLogFile = "{}youtubeLogs.txt".format(self.youtubeLogsFolder)

        #Check folder existence
        self.checkAndCreateFolders()

        #Create logger instance
        self.obj = Logs(self.youtubeLogFile)

    def checkAndCreateFolders(self):
        """Create project youtube folders
        """
        #If parent folder does not exists, create parent and all sub-folders
        if not os.path.exists(self.parentFolder):
            self.createFolder(self.parentFolder)
            self.createFolder(self.youtubeDownloadFolder)
            self.createFolder(self.youtubeAudioFolder)
            self.createFolder(self.youtubeVideoFolder)
            self.createFolder(self.youtubeLogsFolder)
        #Else check and create sub-folders
        elif not os.path.exists(self.youtubeDownloadFolder):
            self.createFolder(self.youtubeDownloadFolder)
        elif not os.path.exists(self.youtubeAudioFolder):
            self.createFolder(self.youtubeAudioFolder)
        elif not os.path.exists(self.youtubeVideoFolder):
            self.createFolder(self.youtubeVideoFolder)
        elif not os.path.exists(self.youtubeLogsFolder):
            self.createFolder(self.youtubeLogsFolder)

    def createFolder(self,folder):
        """
        Input : folder to be created
        """
        try:
            print("Creating {}".format(folder))
            os.makedirs(folder)
        except Exception as e:
            print(e)
            print("Unable to create {}. Please check storage space and permissions")
            print("Exiting from script")
            sys.exit(-1)

    def runCmd(self,cmd,*argv):
        """Function to run command and return output and result
        Input : cmd
        Output : (output,statusCode)
        """
        self.obj.logger.info(cmd)
        try:
            output = sp.check_output(cmd,shell=True,text=True)
            statusCode = 0
            self.obj.logger.info(output) if len(argv) else None
        except sp.CalledProcessError as e:
            self.obj.logger.error("Fail to run {} cmd".format(cmd))
            #self.obj.logger.error(e)
            statusCode = e.returncode
            output = e.output

        return(output,statusCode)

    def regEx(self,data,pattern):
        """
        Input : data, pattern
        Output : searched pattern
        """
        try:
            return(re.search(pattern,data))
        except Exception as e:
            self.obj.logger.error("Not able to find pattern in the data")
            return(1)

    def installYoutbedlAvconv(self):
        """Function to install youtubedl and avconv
        """
        cmd = "wget https://yt-dl.org/downloads/latest/youtube-dl -O /usr/local/bin/youtube-dl"
        self.obj.logger.info("Installing youtubedl")
        (output,statusCode) = self.runCmd(cmd)
        if(output != 0):
            self.obj.logger.error("Failed to install Youtube-Dl. Exiting!!")
            return(1)
        else:
            cmd = "apt-get install libav-tools"
            self.obj.logger.info("Installing avconv")
            (output,statusCode) = self.runCmd(cmd)
            if(output != 0):
                self.obj.logger.error("Failed to install Avconv. Exiting!!")
                return(1)

    def checkForUpdate(self):
        """function to check YoutubeDl version
        """
        cmd = "youtube-dl --version"
        (output,statusCode) = self.runCmd(cmd)
        if(statusCode == 0):
            self.obj.logger.info("Current youtube-dl version is {}".format(output.strip()))
        else:
            self.obj.logger.debug("Can not get current Youtube-Dl version")

        self.obj.logger.info("Checking for any updates")
        cmd = "youtube-dl -U"
        (output,statusCode) = self.runCmd(cmd)
        if(statusCode == 0):
            #pdb.set_trace()
            version = self.regEx(output.strip(),r'[\d.]+').group(0)
            self.obj.logger.info("Updated version is {}".format(version))
        else:
            self.obj.logger.debug("Can not update Youtube-Dl to latest version")


    def checkYoutubeDl(self):
        """Function to check if youtube-dl exists or not.
           If not then call install youtube-dl and avconv()
        """
        error = 0
        ytdl = "which youtube-dl"
        avconv = "which avconv"
        if not os.system(ytdl) and not os.system(avconv):
            self.obj.logger.info("Youtube-dl and avconv are present")
            #Check for update
            self.checkForUpdate()
        else:
            self.obj.logger.info("Youtube-dl and avconv are not present")
            if self.installYoutbedlAvconv():
                error = 1
        return(error)

    def checkFileExists(self,filename,folder):
        """Function to check if downloaded file already exists
        """
        #Since filename is absolute path, extract the filename only using split function
        fileToRemove = folder+'/'+filename.split('/')[-1]
        return (os.path.exists(fileToRemove))

    def moveAudioVideoFiles(self):
        """Function to move mp3 and mp4 files to audio and video folder
        """
        error = 0
        dictionary = {self.youtubeAudioFolder : '*mp3', self.youtubeVideoFolder : '*mp4'}

        for folder,format in dictionary.items():
            for filename in glob.glob(self.youtubeDownloadFolder+format):
                try:
                    if not self.checkFileExists(filename,folder):
                        shutil.move(filename,folder)
                except Exception as e:
                    self.obj.logger.error("Error while moving {} to {}".format(filename, folder))
                    error = 1

        return(error)

    def displayFiles(self):
        """Function to display downloaded audio and video files
        """
        filesDict = {'audio' : self.youtubeAudioFolder , 'video' : self.youtubeVideoFolder}

        for format,folder in filesDict.items():
            self.obj.logger.info("List of {} files".format(format))
            for file in glob.glob(folder+'/*'):
                self.obj.logger.info(file)

    def removeFiles(self):
        """Function to remove files containing ' ' and '&' in their filename from youtube download folder
        """
        for filename in glob.glob(self.youtubeDownloadFolder+"*mp*"):
            if '&' in filename or ' ' in filename:
                os.remove(filename)

    def downloadLink(self):
        """Function to download youtube link.
        """
        error = 0
        for link in self.links:
            self.obj.logger.info("Going to download : {}".format(link))
            #restrict filename option is to create a file with ASCII char only. No space and & in filename
            cmd = r"youtube-dl -o '{}%(title)s.%(ext)s' --restrict-filenames -k -x --audio-quality 2 --audio-format mp3 -f mp4 {}".format(self.youtubeDownloadFolder,link)
            (output,statusCode) = self.runCmd(cmd,1)
            if(statusCode != 0):
                self.obj.logger.error("Fails to download link : {}".format(link))
                error = 1
            #above command will create two files.One downloaded and one which is modified using restrict filename option
            #Remove file which contains space and & in file name
            self.removeFiles()

        return(error)

    def cleanUp(self):
        """Function to delete any duplicate audio and video files from downloads folder
        """
        for file in glob.glob(self.youtubeDownloadFolder+'*mp*'):
            os.remove(file)

    def isLinkPreviouslyDownloaded(self):
        """Function to check if given youtube link is already downloaded.
        """
        return(False)

    def runYoutube(self):
        error = 0
        # Define the steps here
        if self.checkYoutubeDl():
            error = 1
        if not self.isLinkPreviouslyDownloaded():
            if self.downloadLink():
                error = 1
            if self.moveAudioVideoFiles():
                error = 1
            self.cleanUp()

        self.displayFiles()


        return error


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


def getArgs():
    """
    Function to get Command line arguments.
    Should show help if required no. of args are not passed.
    """
    parser = argparse.ArgumentParser(description='Provide youtube link to download. Script will download video and will also convert it to audio file.', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-l','--link',dest='link',help='Single or multiple links separated by csv or a file containing youtube links per line',required=True)
    args = parser.parse_args()
    return args.link

if __name__ == "__main__":
    #Get arguments from cmd line
    link = getArgs()
    #setting status initial value to 0
    status = 0
    ytObj = Youtubedl(link)
    status = ytObj.runYoutube()
    #ytObj.save_to_youtube_downloads_folder()
    print("Test finished with return status as {}".format(status))
    sys.exit(status)
