#!/usr/bin/python
try:
    import os,sys,time
    import glob
    import subprocess as sp
    import argparse
    import re
    import threading
    import glob
    import pdb
    from logModule import Logs
except ImportError:
    raise ImportError("\n -E- Encountered import python exception!!!")

class Youtubedl(object):
    """Using youtube-dl to download the audio and video of the given link
    """
    def __init__(self,link):
        self.links = link.split(',')
        self.logfile = "youtube_logs.txt" # Log file to store all the logs when script is run.
        self.obj = Logs(self.logfile) #Create logger instance
        self.err = 0 #Default return status of the test
        self.current_download_folder = "/home/neo/public_html/myDrive/youtube_downloads"
        self.audio_folder = "/home/neo/public_html/myDrive/youtube_downloads/audio"
        self.video_folder = "/home/neo/public_html/myDrive/youtube_downloads/video"

    def install_youtbedl_avconv(self):
        """Function to install youtubedl and avconv
        """
        ytCmd = "sudo wget https://yt-dl.org/downloads/latest/youtube-dl -O /usr/local/bin/youtube-dl"
        avCmd = "sudo apt-get install libav-tools"
        try:
            self.obj.logger.info("Installing youtubedl using below command")
            self.obj.logger.info(ytCmd)
            result = sp.check_output(ytCmd,shell=True)
            self.obj.logger.info(result)
        except Exception as e:
            self.obj.logger.error(e)
            self.obj.logger.error("Fail to install youtubedl. Exiting !!!")
            self.err = 1
            return self.err
        try:
            self.obj.logger.info("Installing avconv using below command")
            self.obj.logger.info(avCmd)
            result = sp.check_output(avCmd,shell=True)
            self.obj.logger.info(result)
        except Exception as e:
            self.obj.logger.error(e)
            self.obj.logger.error("Fail to install avconv. Exiting !!!")
            self.err = 1
            return self.err

    def check_for_update(self):
        """function to check for the update
        """
        current_version = "youtube-dl --version"
        result = sp.check_output(current_version,shell=True)
        self.obj.logger.info("Current youtube-dl version is {}".format(result.strip()))
        self.obj.logger.info("Checking for any updates")
        update_version = "sudo youtube-dl -U"
        result = sp.check_output(update_version,shell=True)
        self.obj.logger.info("Updated version is {}".format(result.strip()))


    def check_youtube(self):
        """Function to check if youtube-dl exists or not.
           If not then call install youtube-dl and avconv()
        """
        ytdl = "which youtube-dl" 
        avconv = "which avconv"
        if (not(os.system(ytdl)) and not(os.system(avconv))):
            self.obj.logger.info("Youtube-dl and avconv are present")
            #Check for update
            #self.check_for_update()
        else:
            self.obj.logger.info("Youtube-dl and avconv are not present")
            self.install_youtbedl_avconv()

    def downloads_folder(self):
        """Function to check if youtube download folder exists or not.
           If not then create the folders.
        """
        if os.path.exists(self.audio_folder) and os.path.exists(self.video_folder):
            self.obj.logger.info("Youtube audio downloads Folder : {}".format(self.audio_folder))
            self.obj.logger.info("Youtube video downloads Folder : {}".format(self.video_folder))
        else:
            self.obj.logger.info("Creating audio and video Downloads Folder")
            try:
                os.makedirs(self.audio_folder)
                os.makedirs(self.video_folder)
            except Exception as e:
                self.obj.logger.error(e)
                self.obj.logger.error("Failed to create Yotube Donwload Folder. Exiting !!!")
                self.err = 1

    def move_files(self,files_list,folder):
        for files in files_list:
            self.obj.logger.info("Moving {} to {}".format(files,folder))
            try:
                os.rename('{}'.format(files),'{}/{}'.format(folder,os.path.basename(files)))
            except Exception as e:
                self.obj.logger.error(e)
                self.obj.logger.error("Failed to move downloaded files to youtube download folder")
                self.err = 1

    def save_to_youtube_downloads_folder(self):
        """Function to save downloaded videos and audios to youtube-download folder
        """
        self.obj.logger.info("Saving downloaded audio files to {} ".format(self.audio_folder))
        self.obj.logger.info("Saving downloaded video files to {} ".format(self.video_folder))
        mp3_files = glob.glob(r"{}/*.mp3".format(self.current_download_folder))
        mp4_files = glob.glob(r"{}/*.mp4".format(self.current_download_folder))
        self.move_files(mp3_files,self.audio_folder)
        self.move_files(mp4_files,self.video_folder)

    def list_all_downloads(self):
        #folder_list = [self.audio_folder,self.video_folder]
        #for folder in folder_list:
        result = glob.glob("{}/*.mp[3|4]".format(self.current_download_folder))
            #self.obj.logger.info("List of donwloaded files in {}".format(folder))
            #for downloaded in result:
        self.obj.logger.info(result)


    def download_link(self):
        """Function to download youtube link.
        """
        #pdb.set_trace()
        for link in self.links:
            self.obj.logger.info("Going to download : {}".format(link))
            cmd = r"youtube-dl -o '{}/%(title)s.%(ext)s' -k -x --audio-quality 2 --audio-format mp3 -f mp4 {}".format(self.current_download_folder,link)
            self.obj.logger.info(cmd)
            try:
                result = sp.check_output(cmd,shell=True)
                self.obj.logger.debug(result)
                #self.save_to_youtube_downloads_folder()
            except Exception as e:
                self.obj.logger.error(e)
                self.obj.logger.error("Failed to download youtube video and audio!!!")
                self.err = 1
        #self.save_to_youtube_downloads_folder()
        self.list_all_downloads()


    def runYoutube(self):
        # Define the steps here
        self.check_youtube()
        self.downloads_folder()
        self.download_link()
        #self.save_to_youtube_downloads_folder()
        return self.err


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
    ytObj = Youtubedl(link)
    status = ytObj.runYoutube()
    ytObj.save_to_youtube_downloads_folder()
    print "Test finished with return status as {}".format(status)
    sys.exit(status)



