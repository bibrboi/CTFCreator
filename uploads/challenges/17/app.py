
from flask import Flask, request, render_template_string
import sqlite3

app = Flask(__name__)

# Connect to the SQLite database
conn = sqlite3.connect('diary.db')
c = conn.cursor()

# Create table
c.execute('''CREATE TABLE IF NOT EXISTS diary
             (id INTEGER PRIMARY KEY, user TEXT, entry TEXT)''')

# Insert some sample data
c.execute("""INSERT OR IGNORE INTO diary (id, user, entry) VALUES
            (1, 'user1', 'This is user1's diary entry'),
            (2, 'admin', 'This is the admin's secret diary entry'),
            (3, 'user2', 'This is user2's diary entry')""")
conn.commit()
conn.close()

# Render the diary entry page
template = '''
<html>
  <body>
    <h1>Diary Entry {{ entry_id }}</h1>
    <p>{{ entry }}</p>
  </body>
</html>
'''

@app.route('/diary/<int:entry_id>')
def show_diary_entry(entry_id):
  conn = sqlite3.connect('diary.db')
  c = conn.cursor()
  c.execute('SELECT user, entry FROM diary WHERE id = ?', (entry_id,))
  row = c.fetchone()
  conn.close()
  if row:
    return render_template_string(template, entry_id=entry_id, entry=row[1])
  else:
    return 'Diary entry not found'

if __name__ == '__main__':
  app.run(debug=True)
