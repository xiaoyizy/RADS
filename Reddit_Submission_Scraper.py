''' Reddit Submission Scraper -- This script gets every new submission from the specified
subreddits and creates two csv files. The first file contains every unique submission, created
while the script was running, on a separate row. The second file contains every submission
in the first file, with separate rows for the values at each time interval (i.e, score, num_comments, etc.).
'''

import traceback
import multiprocessing as mp
import csv
import queue
import sys
import praw
import time
from datetime import datetime, timedelta, timezone

fields = ['id', 'author', 'score', 'title', 'selftext', '_comments_by_id',
          'created_utc', 'num_comments', 'num_crossposts',
          'over_18', 'permalink', 'url', 'subreddit', 'subreddit_id',
          'subreddit_subscribers', 'stickied',
          'gilded', 'is_self']
all_fields = ['comment_karma', 'link_karma', 'time_retrieved_utc',
              'minutes'] + fields

# Time intervals to check each submission at:
mins_list = [5, 10, 15, 30, 60] + [120 + 60 * k for k in range(23)]

def load_reddit():
# The credentials in the Reddit instance below must be filled in, or stored in a separate .ini file
    reddit = praw.Reddit(user_agent='',
                         client_id='',
                         client_secret='',
                         username='',
                         password='')
    return reddit


# Store fields for current submission in a dict
def sub_to_dict(sub, t, minutes, use_karma = False):
    global fields
    sub_dict = dict()
    for field in fields:
        sub_dict[field] = getattr(sub, field)
    sub_dict['time_retrieved_utc'] = int(t.timestamp())
    sub_dict['minutes'] = minutes
    sub_dict['comment_karma'] = sub.author.comment_karma if use_karma else ''
    sub_dict['link_karma'] = sub.author.link_karma if use_karma else ''
    return sub_dict

# Write submissions/fields to rows of the csv
def bulk_write_subs(reddit, writer, fullnames, q_entries, t) :
    global mins_list
    try :
        subs = reddit.info(fullnames)
        for i,sub in enumerate(subs) :
            writer.writerow(sub_to_dict(sub,t,mins_list[q_entries[i][1]]))
    except Exception as e:
        exc_info = sys.exc_info()
        traceback.print_exception(*exc_info)
        print('Info Exception', e)
        raise e

# Get new submissions
def stream_processor(subred, q):
    global all_fields, mins_list
    reddit = load_reddit()
    fname = 'stream_%s_%s.csv' % (subred, datetime.now().strftime('%Y-%m-%d_%H%M%S'))
    has_started = False
    try:
        with open(fname, 'w', newline='', encoding='utf-8', buffering=1) as out_file:
            writer = csv.DictWriter(out_file, fieldnames=all_fields)
            writer.writeheader()
            for submission in reddit.subreddit(subred).stream.submissions():
                t = datetime.now().astimezone()
                sub_dict = sub_to_dict(submission, t, 0, use_karma=True)
                t_c = datetime.utcfromtimestamp(sub_dict['created_utc'])
                t_c = t_c.replace(tzinfo=timezone.utc)
                t_c = t_c.astimezone()
                if t_c + timedelta(minutes=1) > t:
                    has_started = True
                if has_started:
                    writer.writerow(sub_dict)
                    q_entry = (t + timedelta(minutes=mins_list[0]), 0, sub_dict['id'], submission.fullname)
                    q.put(q_entry)
    except Exception as e:
        exc_info = sys.exc_info()
        traceback.print_exception(*exc_info)
        print('Stream Exception', e)
        raise e

# Get updated fields of old submissions
def score_processor(subred, q):
    global all_fields, mins_list
    pq = queue.PriorityQueue()
    reddit = load_reddit()
    fname = 'score_%s_%s.csv' % (subred, datetime.now().strftime('%Y-%m-%d_%H%M%S'))
    try:
        with open(fname, 'w', newline='', encoding='utf-8', buffering=1) as out_file:
            writer = csv.DictWriter(out_file, fieldnames=all_fields)
            writer.writeheader()
            while True:
                t = datetime.now().astimezone()
                if not q.empty():
                    pq.put(q.get())
                if not pq.empty():
                    q_entries = []
                    while len(q_entries) < 100 and pq.queue[0][0] < t:
                        q_entries.append(pq.get())
                    if q_entries:
                        fullnames = [str(a[3]) for a in q_entries]
                        print('fullnames',fullnames)
                        sys.stdout.flush()
                        bulk_write_subs(reddit, writer, fullnames, q_entries, t)

                        for (q_t, idx, sub_id, fullname) in q_entries :
                            if idx + 1 < len(mins_list):
                                delta = timedelta(minutes=mins_list[idx + 1] - mins_list[idx])
                                q_entry = (t + delta, idx + 1, sub_id, fullname)
                                pq.put(q_entry)
    except Exception as e:
        exc_info = sys.exc_info()
        traceback.print_exception(*exc_info)
        print('Score Exception', e)
        raise e


def main():
    q = mp.Queue()
    # Subreddits can be entered as a command line argument, or hard-coded.
    # In either case, multiple subreddits should be separated by '+' as the line below shows.
    #subred = sys.argv[1]
    subred = 'AskReddit+Pics+Gifs+Videos+WorldNews+Funny+Aww+gaming'
    mp.Process(target=score_processor, args=(subred, q)).start()
    mp.Process(target=stream_processor, args=(subred, q)).start()


if __name__ == "__main__":
    main()
