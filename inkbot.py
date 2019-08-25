#!/usr/bin/python3

import time
import re
import warnings
import shelve
import traceback

import praw
from praw.exceptions import APIException
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

        # Compile the regexes in the inklist; this speeds up search time by ~20x
        for ink in self.inklist:
            ink["compiled_re"] = re.compile(ink["fields"]["RegEx"], flags=re.IGNORECASE)

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
                print(f"Logged in as '{self.r.user.me()}'")
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
        retries = 20
        while retries > 1:
            try:
                reply = comment.reply(output)
                break
            except APIException as e:
                if self.debug:
                    print(f"Got PRAW exception '{e}' while trying to reply")
                retries -= 1
                time.sleep(self.wait_time)
                if retries < 1:
                    print(f"Out of retries. Restarting InkBot")
                    self.___handle_exception(e)
            except Exception as e:
                # Crash right away if encountering a non-API exception
                if self.debug:
                    print(f"Got non-API exception '{e}' while trying to reply")
                self.___handle_exception(e)
        self.PostList[str(comment.id)] = str(reply.id)
        self.PostList.sync()

# This is the action that is performed on a comment when it is detected.
    def __comment_action(self, c):
        regex = r"\[\[.*?\]\]"
        text = c.body
        output = ''
        sid = str(c.id)

        # The new "fancypants" reddit comment editor escapes braces with a leading
        # backslash. Solve this problem by stripping backslashes from the body text
        text = text.replace("\\", "")

        if sid in self.PostList:
            # Already replied to this post, do not process further
            return

        match_list = re.findall(regex, text)
        if not match_list:
            # Did not find any matches, do not process further
            return

        # At this point, we are ready to go over every match found and compare them to our inklist regex for commenting
        for match in match_list:
            # Walk over the inklist, it is a list of lists, so we need two for loops
            for ink in self.inklist:
                # Build up the regex, pulled from the Airtable
                ink_regex = ink.get("compiled_re")
                # Build up the replacement string from Airtable
                ink_name = ink["fields"].get("Ink Name")
                if self.version == 4 and ('Scanned Page' in ink['fields']):
                    ink_url = ink["fields"]["Scanned Page"][0]["url"]
                else:
                    ink_url = ink["fields"].get("Imgur Address")
                if not all([ink_regex, ink_name, ink_url]):
                    # Stop trying to process ink if unable to get all required fields
                    continue
                ink_link_text = f"*  [{ink_name}]({ink_url})   \n"
                # will enter this if statement if the specific match from the comment matches this Airtable entry
                if ink_regex.search(match):
                    if self.debug:
                        print("Found Match")
                        print(f"Found '{ink_regex}' in '{match}'")
                    output = output + ink_link_text
        # After processing all matches, and building up the output, post as a reply
        if output:
            # Note that empty strings are falsey; an output of "" will not be posted
            self.__reply_to(c, output)


    def __inkbot_loop(self):
        try:
            # Start the comment stream for processesing
            for comment in self.r.subreddit(self.subreddit).stream.comments():
                self.__comment_action(comment)
        except (KeyboardInterrupt, SystemExit):
            if self.debug:
                print("\nKeyboard exit or System Exit, closing DB file\n")
            self.PostList.close()
            raise
        except Exception as e:
            self.___handle_exception(e)





