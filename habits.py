import os
import re
import logging
from datetime import datetime
from dateutil import tz
from todoist.api import TodoistAPI
from todoist.managers.notes import NotesManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TODOIST_DATE_FORMAT = "%Y-%m-%d"


def get_token():
    token = os.getenv('TODOIST_APIKEY')
    if not token:
        raise Exception('Please set the API token in environment variable.')
    return token


class Task(object):
    def __init__(self, api, item, notes, weekstart):
        self.item = item
        self.id = self.item['id']
        self.notes = notes
        self.api = api
        self.summary, self.week, self.streak = self.parse_notes()
        self.weekstart = weekstart

    def parse_notes(self):
        """
        Reads the relevant current notes and returns them
        Adds the note if the note does not exist
        """
        summary = None
        week = None
        streak = None
        for note in self.notes:
            if note['content'].startswith('Summary:'):
                summary = note
            if note['content'].startswith('Weekly:'):
                week = note
            if note['content'].startswith('Streak:'):
                streak = note
        if summary is None:
            summary = self.api.notes.add(self.id, 'Summary: 0/0 | 0%')
        if week is None:
            week = self.api.notes.add(self.id, 'Weekly: 0/0')
        if streak is None:
            streak = self.api.notes.add(self.id, 'Streak: 0 days')

        return summary, week, streak

    def increase_streak(self):
        streak = self.streak
        res = re.search(r'(\d+)', streak['content'])
        current_days = int(res.group(1))
        days = '{}'.format(current_days + 1)
        text = re.sub(r'(\d+)', days, streak['content'])
        streak.update(content=text)
        self.update_content(text)

    def reset_streak(self):
        streak = self.streak
        days = '{}'.format(0)
        text = re.sub(r'(\d+)', days, streak['content'])
        streak.update(content=text)
        self.update_content(text)
    
    def update_week(self, n = 1):
        """
        Increases the week note by n days
        """
        week = self.week
        res = re.search(r'(\d+)\/(\d+)', week['content'])
        if self.weekstart:
            days = '{}/{}'.format(n, 1)
        else:
            cur, tot = int(res.group(1)), int(res.group(2))
            days = '{}/{}'.format(cur + n, tot + 1)
        text = re.sub(r'(\d+)\/(\d+)', days, week['content'])
        week.update(content=text)

    def update_summary(self, n = 1):
        """
        Increases the summary note by n days
        """
        summary = self.summary
        res = re.search(r'(\d+)\/(\d+)', summary['content'])
        cur, tot = int(res.group(1)), int(res.group(2))
        days = '{}/{}'.format(cur + n, tot + 1)
        percentage = '{}%'.format(int(100.0*(cur + n)/(tot +1)))
        text = re.sub(r'(\d+)\/(\d+)', days, summary['content'])
        text = re.sub(r'(\d+)\%', percentage, text)
        summary.update(content=text)

    def update_content(self, content):
        details = self.item['content'].split(' || ')[0]
        text = details + ' || ' + content
        self.item.update(content=text)

    @property
    def due_date(self):
        """
        Get the due date for the current task.
        :return:
        """
        return self.item['due'].get('date')

    def is_due(self, today):
        """
        Check if task is due.
        """
        return today not in self.due_date

    def increase(self):
        """
        Increase streak by 1 day.
        Increase overall by 1 day.
        Increase weekly by 1 day and reset on first day of the week
        """
        self.increase_streak()
        self.update_summary(n=1)
        self.update_week(n=1)
    
    def no_change(self, today):
        """
        Maintains current count and increases number of total days
        """
        self.reset_streak()
        self.update_summary(n=0)
        self.update_week(n=0)
        due_date = self.item['due'].get('date')
        if 'T' in due_date:
            time = due_date.split('T')[1]
            today = today + 'T' + time
        self.item.update_date_complete(due={'string': self.item['due'].get('string'),
                                            'date': today})
        


class Todoist(object):
    def __init__(self):
        self.api = TodoistAPI(get_token())
        self.api.sync()
        self.api.notes = NotesManager(self.api)
        habit_label_ids = [label['id'] for label in self.api.state['labels'] if label['name']=='habit']
        assert (len(habit_label_ids)==1)
        self.habit_label_id = habit_label_ids[0]
        self.habits = self.get_habits()
        print (self.habits)
        self.get_datetime()
        

    def get_datetime(self):
        timezone = self.api.state['user']['tz_info']['timezone']
        tz_location = tz.gettz(timezone)
        now = datetime.now(tz=tz_location)
        self.weekstart = datetime.weekday(now) == self.api.state['user']['start_day'] #Checks if yesterday was the week start day
        self.today = now.strftime(TODOIST_DATE_FORMAT)

    def get_habits(self):
        habits = []
        for item in self.api.state['items']:
            if self.habit_label_id in item['labels']:
                habits.append(item)
        return habits

    def update_habit(self):
        for item in self.habits:
            notes = [note for note in self.api.state['notes'] if note['item_id'] == item['id']]
            task = Task(self.api, item, notes, self.weekstart)
            if task.is_due(self.today):
                task.no_change(self.today)
            else:
                task.increase()
        self.api.commit()


def main():
    todo = Todoist()
    todo.update_habit()


if __name__ == '__main__':
    main()
