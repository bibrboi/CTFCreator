from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
db = SQLAlchemy(app)
class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    flag = db.Column(db.String(100), nullable=False)
@app.route('/employees', methods=['GET'])
def get_employees):
    name = request.args.get('name')
    employees = Employee.query.filter_by(name=name).all()
    output = []
    for employee in employees:
        employee_data = {'id': employee.id, 'name': employee.name, 'email': employee.email}
        output.append(employee_data)
    return jsonify({'employees': output})
@app.route('/add_employee', methods=['POST'])
def add_employee):
    new_employee = Employee(name=request.json['name'], email=request.json['email'], flag='CTF{sql_injection_is_fun}')
    db.session.add(new_employee)
    db.session.commit()
    return jsonify({'message': 'New employee added!'})
if __name__ == '__main__':
    app.run(debug=True)
