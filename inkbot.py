#!/usr/bin/python3

import time
import re
import warnings
import praw
import shelve
import traceback
from airtable.airtable import Airtable

warnings.simplefilter('ignore')

def download_airtable(key, base, table_name):
    """Download all of the rows from an Airtable table

    Parameters
    ==========
    key : string
        The API key for the Airtable that will be downloaded
    base : string
        The ID of the Airtable Base containing the table you wish to download
    table_name : string
        The name of the table you wish to download

    Returns
    =======
    row_list : list
        A list of collections.OrderedDict objects, one for each row in the table
    """
    at = Airtable(base, key)
    resp = at.get(table_name)
    row_list = resp.get("records")
    offset = resp.get("offset")
    while offset:
        resp = at.get(table_name, offset=offset)
        row_list.extend(resp.get("records"))
        offset = resp.get("offset")
    return row_list

# This is a class for inkbot find and respond with a link to an image of an ink
# On init, this class needs:
#     a Reddit User Name, Password, User Agent, and subreddit
#     an AirTable Key, Base, and Table
#     optionally a user can specify a lower limit to the number of comments and change
#     the wait time (in seconds) for exceptions.  The default is 2 minutes (60 seconds), 
#     however, the user may wish to increase this time
class InkBot:
    def __init__(self,
                 user_agent,
                 user_name,
                 user_pass,
                 client_id,
                 client_secret,
                 subreddit,
                 at_key,
                 at_base,
                 at_table,
                 limit=1000,
                 wait_time = 60,
                 version = 4,
                 debug=False ):

        self.debug = debug

        if self.debug:
            print("Setting up Inkbot....")

        self.user_agent    = user_agent
        self.user_name     = user_name
        self.user_pass     = user_pass
        self.client_id     = client_id
        self.client_secret = client_secret
        self.at_base       = at_base
        self.at_key        = at_key
        self.at_table      = at_table
        self.subreddit     = subreddit
        self.limit         = limit
        self.wait_time     = wait_time
        self.version       = version


    # Start things up
    def start(self):
        if self.debug:
            print("Inkbot Logging into Reddit...")
        self.__login()

        if self.debug:
            print("Getting Inks from Airtable...")
        # Populate the Ink table from Airtable
        self.inklist = download_airtable(self.at_key, self.at_base, self.at_table)

        if self.debug:
            print("Getting replied to posts from db...")
        # open up our comment database
        self.PostList = shelve.open('inkbot_list.db')

        if self.debug:
            print("Going into Main Loop...")
        self.__inkbot_loop()
     
    # Login to Reddit
    def __login(self):
        try:
            self.r = praw.Reddit(client_id = self.client_id,
                                 client_secret = self.client_secret,
                                 password = self.user_pass,
                                 user_agent = self.user_agent,
                                 username = self.user_name)
            if self.debug:
                print(self.r.user.me())
        except Exception as e:
            self.___handle_exception(e)

# Handle our exceptions.  This is the point where when things go bad we come.  What we are doing here is
# a bit of cleanup, and then we are sleeping the wait time passed in at init.  After that we are trying to
# restart things.   Hopefully this will happen until reddit is responsive again
    def ___handle_exception(self, e):
        if self.debug:
            traceback.print_exc()
            print("Inkbot had an Error: {}, going to try and continue".format(e))
        self.PostList.close()
        time.sleep(self.wait_time)
        self.start()
        exit()

# This is the function to reply to comments, comment out the comment.reply line to be able to test
# without posting to the subreddit, if self.debug == True, it will print to the command line the 
# output
    def __reply_to(self, comment, output):
        # Debug prints, show up on the host running this bot
        if self.debug:
            print("\n---------------------------------------------")
            print("%s" %(output))
            print("\n---------------------------------------------")
        reply = comment.reply(output)
        self.PostList[str(comment.id)] = reply
        self.PostList.sync()

# This is the action that is performed on a comment when it is detected.
    def __comment_action(self, c):
        regex = r"\[\[.*?\]\]"
        text = c.body
        output = ''
        sid = str(c.id)
    
        # We will enter this if statement only if the [[ink name]] is found in the body of the post, else we just move on
        if re.search(regex, text):
           # Next we check to see if we have processed this comment in the past
           if sid not in self.PostList:
                # Now we create a list with all of the matches in the body of the comment
                matchList = re.findall(regex, text)
                found_match = False 
                # At this point, we are ready to go over every match found and compare them to our inklist regex for commenting
                for match in matchList:
                    # Walk over the inklist, it is a list of lists, so we need two for loops
                    for ink in self.inklist:
                        # Build up the regex, pulled from the Airtable
                        temp_reg='\[\[' + ink['fields']['Brand+ink regex'] + '\]\]'
                        # Build up the replacement string from Airtable
                        ink_name = ink["fields"]["Name"]
                        if self.version == 4 and ('Scanned Page' in ink['fields']):
                            ink_url = ink["fields"]["Scanned Page"][0]["url"]
                        else:
                            ink_url = ink['fields']['Imgur Address']
                        ink_link_text = f"* [{ink_name}]({ink_url})   \n"
                        # will enter this if statement if the specific match from the comment matches this Airtable entry
                        if re.search(temp_reg, match, flags=re.IGNORECASE):
                            if self.debug:
                                print("Found Match")
                            found_match = True 
                            output = output + ink_link_text
                # After processing all matches, and building up the output, post
                if found_match:
                    # retries for if reddit says we are posting too much, this gives us a 20min retry for posts
                    retries = 20
                    while retries > 0:
                        try:
                        # Post comment to reddit and add this post ID to our responded to comment database
                            self.__reply_to(c, output)
                            break  # exit the loop
                        except Exception as e:
                            if self.debug:
                                traceback.print_exc()
                                print("######Sleep Exception######")
                        time.sleep(self.wait_time)
                        retries -= 1
                    # Treat running out of retries as an exception
                    self.___handle_exception(e)

    def __inkbot_loop(self):
        try:
            # Start the comment stream for processesing
            # DELETE ME--Old methodology, keep for now, delete line next update
            #for self.comment in praw.helpers.comment_stream(self.r, self.subreddit, limit=self.limit):
            for self.comment in self.r.subreddit(self.subreddit).stream.comments():
                self.__comment_action(self.comment)
        except (KeyboardInterrupt, SystemExit):
            if self.debug:
                print("\nKeyboard exit or System Exit, closing DB file\n")
            self.PostList.close()
            raise
        except Exception as e:
            self.___handle_exception(e)





