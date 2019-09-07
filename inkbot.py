#!/usr/bin/python3

import time
import re
import warnings
import shelve
import traceback
from pathlib import Path

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

def find_best_match(inklist, token):
    """Find the ink that matches `token` the closest

    Some of ink strings can have multiple regular expressions that find a match on
    them. Find all of the matches, and then return the match with the longest
    matching substring.

    Parameters
    ==========
    inklist : list of OrderedDict objects
        A list of OrderedDict objects containing information about each ink, as well as
        a compiled regular expression (`compiled_re`) describing how the ink should be
        matched
    token : string
        The string that the user populated to have InkBot match on

    Returns
    =======
    best_match : OrderedDict
        An OrderedDict from `self.inklist` containing the best matching row

    """
    candidate_matches = []
    for ink in inklist:
        ink_regex = ink.get("compiled_re")
        if not ink_regex:
            # Somehow compiled regex didn't get populated...
            continue
        match = ink_regex.search(token)
        if match:
            candidate_matches.append((match, ink))
    best_match = None
    # Force matching substr to be at least 5 characters
    longest_substr = 5
    for match, ink in candidate_matches:
        substr_len = len(match.group(0))
        if substr_len > longest_substr:
            longest_substr = substr_len
            best_match = ink
    return best_match

def format_comment(ink_matches):
    """Builds an InkBot comment based on the list of matched inks

    Given a list of "ink" OrderedDict objects, extract the properties needed to build
    up an InkBot reply; namely the full ink Name and a URL to the ink's swab

    Parameters
    ==========
    ink_matches : list of OrderedDict objects
        A list of OrderedDict objects containing information about each ink

    Returns
    =======
    reply_body : string
        A reply string composed of a list of inks and links to their swabs

    """
    reply_body = ""
    for ink in ink_matches:
        if not ink:
            # Skip non-matching inks
            continue
        ink_name = ink["fields"].get("Ink Name")
        if "Scanned Page" not in ink["fields"]:
            ink_url = ink["fields"].get("Imgur Address")
        else:
            scanned_page = ink["fields"].get("Scanned Page")
            ink_url = scanned_page[0]["url"]
        if not (ink_name and ink_url):
            # Problem extracting name and/or URL
            # TODO: log this
            continue
        row = f"* [{ink_name}]({ink_url})\n"
        reply_body = reply_body + row

    return reply_body

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
                 working_dir = ".",
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
        self.working_dir   = Path(working_dir)
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
        ink_list_pth = self.working_dir / "inkbot_list.db"
        self.PostList = shelve.open(str(ink_list_pth))
        if self.debug:
            #TODO: Log!
            print(f"Opened {ink_list_pth} and found {len(self.PostList.keys())} keys")

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
        sid = str(c.id)

        if sid in self.PostList:
            # Already replied to this post, do not process further
            return

        # The new "fancypants" reddit comment editor escapes braces with a leading
        # backslash. Solve this problem by stripping backslashes from the body text
        text = text.replace("\\", "")

        match_list = re.findall(regex, text)
        if not match_list:
            # Did not find any matches, do not process further
            return

        ink_matches = [find_best_match(self.inklist, token) for token in match_list]
        comment_body = format_comment(ink_matches)

        if comment_body:
            self.__reply_to(c, comment_body)



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





