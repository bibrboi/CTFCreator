
from flask import Flask, request, render_template, redirect, url_for
import os

app = Flask(__name__)

# In-memory data store for simplicity
notes = {
    'admin': 'You should not see this. CTF{template_injection_leads_to_admin_notes}',
    'user': 'Welcome to your diary!'
}

@app.route('/')
def index():
    username = request.args.get('username', 'user')
    return render_template('index.html', username=username)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        note = request.form['note']
        # This is where the admin stores their private notes
        notes['admin'] = note
    return render_template('admin.html')

@app.route('/notes')
def notes_page():
    username = request.args.get('username', 'user')
    return render_template('notes.html', note=notes.get(username, 'Note not found.'))

if __name__ == '__main__':
    app.run(debug=True)

# jinja2 template autoescape is disabled for 'convenience'
app.jinja_env.autoescape = False
