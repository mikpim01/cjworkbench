import tweepy
from tweepy import TweepError
import pandas as pd
import os, re
from .moduleimpl import ModuleImpl
from server.versions import save_fetched_table_if_changed

# ---- Twitter import module ----

class Twitter(ModuleImpl):

    # Must match order of items in twitter.json module def
    QUERY_TYPE_USER = 0
    QUERY_TYPE_SEARCH = 1
    QUERY_TYPE_LIST = 2

    # Get dataframe of last tweets fron our storage,
    @staticmethod
    def get_stored_tweets(wf_module):
        return wf_module.retrieve_fetched_table()

    # Get from Twitter, return as dataframe
    @staticmethod
    def get_new_tweets(wfm, querytype, query, old_tweets):

        # Authenticate with "app authentication" mode (high rate limit, read only)
        consumer_key = os.environ['CJW_TWITTER_CONSUMER_KEY']
        consumer_secret = os.environ['CJW_TWITTER_CONSUMER_SECRET']
        auth = tweepy.AppAuthHandler(consumer_key, consumer_secret)
        api = tweepy.API(auth)

        # Only get last 100 tweets, because that is twitter API max for single call
        if querytype == Twitter.QUERY_TYPE_USER:
            if query[0] == '@':                     # allow user to type @username or username
                query = query[1:]
            statuses = api.user_timeline(query, count=200, tweet_mode='extended')
        elif querytype == Twitter.QUERY_TYPE_SEARCH:
            statuses = api.search(q=query, count=100, tweet_mode='extended')
        else:
            queryparts = re.search('(?:https?://)twitter.com/([A-Z0-9]*)/lists/([A-Z0-9-_]*)', query, re.IGNORECASE)
            if not queryparts:
                raise Exception('not a Twitter list URL')
            statuses = api.list_timeline(queryparts.group(1), queryparts.group(2), count=200, tweet_mode='extended')

        # Columns to retrieve and store from Twitter
        # Also, we use this to figure ou the index the id field when merging old and new tweets
        cols = ['created_at', 'full_text', 'retweet_count', 'favorite_count', 'in_reply_to_screen_name', 'source', 'id']

        tweets = [[getattr(t, x) for x in cols] for t in statuses]
        table = pd.DataFrame(tweets, columns=cols)
        table.insert(0, 'screen_name', [t.user.screen_name for t in statuses])
        table.rename(columns={'full_text':'text'}, inplace=True)  # 280 chars should still be called 'text', meh
        return table


    # Combine this set of tweets with previous set of tweets
    def merge_tweets(wf_module, new_table):
        old_table = Twitter.get_stored_tweets(wf_module)
        if old_table is not None:
            new_table = pd.concat([new_table,old_table]).drop_duplicates(['id']).sort_values('id',ascending=False).reset_index(drop=True)
        return new_table

    # Render just returns previously retrieved tweets
    @staticmethod
    def render(wf_module, table):
        return Twitter.get_stored_tweets(wf_module)


    # Load specified user's timeline
    @staticmethod
    def event(wfm, event=None, **kwargs):
        table = None
        param_names = {
            Twitter.QUERY_TYPE_USER: 'username',
            Twitter.QUERY_TYPE_SEARCH: 'query',
            Twitter.QUERY_TYPE_LIST: 'listurl'
        }

        querytype = wfm.get_param_menu_idx("querytype")
        query = wfm.get_param_string(param_names[querytype])

        if query.strip() == '':
            wfm.set_error('Please enter a query')
            return

        # fetching could take a while so notify clients/users that we're working on it
        wfm.set_busy(notify=True)

        try:

            if wfm.get_param_checkbox('accumulate'):
                old_tweets = Twitter.get_stored_tweets(wfm)
                tweets = Twitter.get_new_tweets(wfm, querytype, query, old_tweets)
                tweets = Twitter.merge_tweets(wfm, tweets)
            else:
                tweets = Twitter.get_new_tweets(wfm, querytype, query, None)

        except TweepError as e:
            if querytype==Twitter.QUERY_TYPE_USER and e.response.status_code==401:
                wfm.set_error('User %s\'s tweets are protected' % query)
                return
            elif querytype==Twitter.QUERY_TYPE_USER and e.response.status_code==404:
                wfm.set_error('User %s does not exist' % query)
                return
            else:
                wfm.set_error('HTTP error %s fetching tweets' % str(e.response.status_code))
                return

        except Exception as e:
            wfm.set_error('Error fetching tweets: ' + str(e))
            return


        if wfm.status != wfm.ERROR:
            save_fetched_table_if_changed(wfm, tweets, '')
