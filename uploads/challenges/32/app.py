from flask import Flask, request, render_template_string
from sqlite3 import SQLite3
import os
app = Flask(__name__)

# Define the database file
DATABASE_FILE = 'secrets.db'

# Create the database if it doesn't exist
if not os.path.exists(DATABASE_FILE):
    db = SQLite3(DATABASE_FILE)
    cursor = db.cursor()
    cursor.execute('CREATE TABLE secrets (id INTEGER PRIMARY KEY, secret TEXT)')
    db.commit()
    db.close()

# Route for the home page
@app.route('/'
, methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        secret = request.form['secret']
        db = SQLite3(DATABASE_FILE)
        cursor = db.cursor()
        cursor.execute('INSERT INTO secrets (secret) VALUES ('{}")'.format(secret))
        db.commit()
        db.close()
        return 'Secret stored successfully'
    return render_template_string('''
    <form method="post">
        <input type="text" name="secret" />
        <input type="submit" value="Store Secret" />
    </form>
    ''')

# Route for viewing secrets
@app.route('/view'
, methods=['GET'])
def view_secrets():
    db = SQLite3(DATABASE_FILE)
    cursor = db.cursor()
    cursor.execute('SELECT * FROM secrets WHERE id = {}'.format(request.args.get('id')))
    secret = cursor.fetchone()
    db.close()
    if secret:
        return secret[1]
    return 'No secret found'

if __name__ == '__main__':
    app.run(debug=True)