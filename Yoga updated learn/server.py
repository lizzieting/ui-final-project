from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
import os
import uuid

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your-secret-key-here'  # Required for flash messages and sessions
db = SQLAlchemy(app)

# Database Model for storing quiz answers
class QuizAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    question_id = db.Column(db.Integer)
    answer = db.Column(db.String(200))
    is_correct = db.Column(db.Boolean)
    quiz_session = db.Column(db.String(36))  # Store session ID

# Load quiz questions from JSON
def load_quiz_data():
    json_path = os.path.join(app.root_path, 'data', 'quiz_data.json')
    with open(json_path, 'r') as f:
        return json.load(f)

quiz_data = load_quiz_data()

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/learn')
def learn():
    json_path = os.path.join(app.root_path, 'data', 'learn_data.json')
    with open(json_path, 'r') as f:
        data = json.load(f)
        flows = data.get("flows", [])  # Get the list under "flows"
    return render_template('learn.html', flows = flows)

@app.route('/flow/<flow_id>')
def flow(flow_id):
    with open(os.path.join(app.root_path, 'data', 'learn_data.json')) as f:
        data = json.load(f)
    flow = next((f for f in data["flows"] if f["id"] == flow_id), None)
    if not flow:
        return "Flow not found", 404
    return render_template('flow.html', flow=flow)


@app.route('/flow/<flow_id>/start')
@app.route('/flow/<flow_id>/start/<int:pose_index>')
def start_flow(flow_id, pose_index=0):
    with open(os.path.join(app.root_path, 'data', 'learn_data.json')) as f:
        data = json.load(f)
    flow = next((f for f in data["flows"] if f["id"] == flow_id), None)
    if not flow or 'poses' not in flow or pose_index >= len(flow['poses']):
        return "Flow not found or pose index out of range", 404

    pose = flow['poses'][pose_index]
    total_poses = len(flow['poses'])
    return render_template('start_flow.html', flow=flow, pose=pose,
                           index=pose_index, total=total_poses)


@app.route('/start-quiz')
def index():
    # Generate a new session ID for this quiz attempt
    session['quiz_session'] = str(uuid.uuid4())
    # Clear previous quiz answers for this session
    QuizAnswer.query.filter_by(quiz_session=session['quiz_session']).delete()
    db.session.commit()
    return redirect(url_for('quiz', question_id=1))

@app.route('/quiz/<int:question_id>', methods=['GET', 'POST'])
def quiz(question_id):
    # Check if there's an active quiz session
    if 'quiz_session' not in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        # Store the answer
        answer = request.form.get('answer')
        if not answer:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Please select an answer'}), 400
            flash('Please select an answer before proceeding.', 'warning')
            return redirect(url_for('quiz', question_id=question_id))
            
        question = quiz_data['questions'][question_id - 1]
        
        # Determine if the answer is correct based on question type
        if question.get('type') == 'image':
            # For image questions, find the selected option and check its 'correct' flag
            selected_option = next((opt for opt in question['options'] if opt['text'] == answer), None)
            is_correct = selected_option and selected_option['correct']
        else:
            # For text questions, compare with the 'correct' field
            is_correct = answer == question['correct']
        
        # Save to database with session ID
        quiz_answer = QuizAnswer(
            question_id=question_id,
            answer=answer,
            is_correct=is_correct,
            quiz_session=session['quiz_session']
        )
        db.session.add(quiz_answer)
        db.session.commit()
        
        # If this is an AJAX request, return JSON response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            next_url = url_for('results') if question_id >= len(quiz_data['questions']) else url_for('quiz', question_id=question_id + 1)
            return jsonify({
                'correct': is_correct,
                'next_url': next_url
            })
        
        # Regular form submission - redirect to next question or results
        if question_id < len(quiz_data['questions']):
            return redirect(url_for('quiz', question_id=question_id + 1))
        else:
            return redirect(url_for('results'))
    
    # GET request - show the question
    if 1 <= question_id <= len(quiz_data['questions']):
        question = quiz_data['questions'][question_id - 1]
        return render_template('quiz.html', 
                             question=question,
                             current_question=question_id,
                             total_questions=len(quiz_data['questions']))
    return redirect(url_for('index'))

@app.route('/results')
def results():
    # Check if there's an active quiz session
    if 'quiz_session' not in session:
        return redirect(url_for('index'))
        
    # Get answers only from the current quiz session
    answers = QuizAnswer.query.filter_by(quiz_session=session['quiz_session'])\
                            .order_by(QuizAnswer.question_id)\
                            .all()
    
    # Calculate score based on current session only
    correct_answers = sum(1 for answer in answers if answer.is_correct)
    total_questions = len(quiz_data['questions'])
    score = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
    
    # Clear the quiz session
    session.pop('quiz_session', None)
    
    return render_template('results.html', 
                         score=score,
                         total=total_questions,
                         correct=correct_answers)

if __name__ == '__main__':
    with app.app_context():
        # Drop all tables and recreate them to ensure the schema is up to date
        db.drop_all()
        db.create_all()
    app.run(debug=True,port = 5001) 
