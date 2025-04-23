from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
import os
import uuid
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your-secret-key-here'  # Required for flash messages and sessions
db = SQLAlchemy(app)

# Configure logging
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/yoga_app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Yoga app startup')

# Database Model for storing quiz answers
class QuizAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    question_id = db.Column(db.Integer)
    answer = db.Column(db.String(200))
    is_correct = db.Column(db.Boolean)
    quiz_session = db.Column(db.String(36))  # Store session ID

# Database Model for storing user progress
class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    page_visited = db.Column(db.String(50))
    time_spent = db.Column(db.Integer)  # Time spent in seconds
    session_id = db.Column(db.String(36))

# Load quiz questions from JSON
def load_quiz_data():
    try:
        json_path = os.path.join(app.root_path, 'data', 'quiz_data.json')
        with open(json_path, 'r') as f:
            data = json.load(f)
            app.logger.info('Successfully loaded quiz data')
            return data
    except FileNotFoundError:
        app.logger.error('Quiz data file not found')
        return {'questions': []}
    except json.JSONDecodeError:
        app.logger.error('Invalid JSON in quiz data file')
        return {'questions': []}

# Load learning content from JSON
def load_learn_data():
    try:
        json_path = os.path.join(app.root_path, 'data', 'learn_data.json')
        with open(json_path, 'r') as f:
            data = json.load(f)
            app.logger.info('Successfully loaded learning data')
            return data
    except FileNotFoundError:
        app.logger.error('Learning data file not found')
        return {'sections': []}
    except json.JSONDecodeError:
        app.logger.error('Invalid JSON in learning data file')
        return {'sections': []}

quiz_data = load_quiz_data()
learn_data = load_learn_data()

def validate_quiz_data(data):
    """Validate the structure of quiz data"""
    if not isinstance(data, dict):
        return False
    if 'questions' not in data:
        return False
    if not isinstance(data['questions'], list):
        return False
    for question in data['questions']:
        if not all(key in question for key in ['text', 'options', 'correct']):
            return False
    return True

@app.route('/')
def home():
    app.logger.info('Home page accessed')
    return render_template('home.html')

@app.route('/learn')
def learn():
    # Log user progress
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    progress = UserProgress(
        page_visited='learn',
        session_id=session['session_id']
    )
    db.session.add(progress)
    db.session.commit()
    
    app.logger.info(f'Learn page accessed by session {session["session_id"]}')
    return render_template('learn.html', sections=learn_data['sections'])

@app.route('/learn/<int:section_id>')
def learn_section(section_id):
    # Log user progress
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    # Find the requested section
    section = next((s for s in learn_data['sections'] if s['id'] == section_id), None)
    if not section:
        app.logger.warning(f'Invalid section ID accessed: {section_id}')
        flash('Section not found', 'error')
        return redirect(url_for('learn'))
    
    progress = UserProgress(
        page_visited=f'learn_section_{section_id}',
        session_id=session['session_id']
    )
    db.session.add(progress)
    db.session.commit()
    
    app.logger.info(f'Learn section {section_id} accessed by session {session["session_id"]}')
    return render_template('learn_section.html', section=section, sections=learn_data['sections'])

@app.route('/start-quiz')
def index():
    # Generate a new session ID for this quiz attempt
    session['quiz_session'] = str(uuid.uuid4())
    # Clear previous quiz answers for this session
    QuizAnswer.query.filter_by(quiz_session=session['quiz_session']).delete()
    db.session.commit()
    
    app.logger.info(f'New quiz session started: {session["quiz_session"]}')
    return redirect(url_for('quiz', question_id=1))

@app.route('/quiz/<int:question_id>', methods=['GET', 'POST'])
def quiz(question_id):
    # Input validation
    if not isinstance(question_id, int) or question_id < 1:
        app.logger.warning(f'Invalid question_id accessed: {question_id}')
        flash('Invalid question number', 'error')
        return redirect(url_for('index'))
    
    # Check if there's an active quiz session
    if 'quiz_session' not in session:
        app.logger.warning('Quiz accessed without active session')
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        # Check if this is a "go back" request
        if 'go_back' in request.form:
            app.logger.info(f'User going back from question {question_id} to {question_id-1}')
            return redirect(url_for('quiz', question_id=question_id-1))
            
        # Validate answer
        answer = request.form.get('answer')
        if not answer:
            app.logger.warning(f'Empty answer submitted for question {question_id}')
            flash('Please select an answer before proceeding.', 'warning')
            return redirect(url_for('quiz', question_id=question_id))
            
        # Validate question exists
        if question_id > len(quiz_data['questions']):
            app.logger.error(f'Question {question_id} not found in quiz data')
            flash('Invalid question', 'error')
            return redirect(url_for('index'))
            
        question = quiz_data['questions'][question_id - 1]
        
        # Determine if the answer is correct based on question type
        if question.get('type') == 'image':
            # For image questions, find the selected option and check its 'correct' flag
            selected_option = next((opt for opt in question['options'] if opt['text'] == answer), None)
            is_correct = selected_option and selected_option['correct']
        else:
            # For text questions, compare with the 'correct' field
            is_correct = answer == question['correct']
        
        # Delete any existing answer for this question in this session
        existing_answer = QuizAnswer.query.filter_by(
            question_id=question_id,
            quiz_session=session['quiz_session']
        ).first()
        
        if existing_answer:
            db.session.delete(existing_answer)
        
        # Save to database with session ID
        quiz_answer = QuizAnswer(
            question_id=question_id,
            answer=answer,
            is_correct=is_correct,
            quiz_session=session['quiz_session']
        )
        db.session.add(quiz_answer)
        db.session.commit()
        
        app.logger.info(f'Answer recorded for question {question_id}: {"correct" if is_correct else "incorrect"}')
        
        # Move to next question or results
        if question_id < len(quiz_data['questions']):
            return redirect(url_for('quiz', question_id=question_id + 1))
        else:
            return redirect(url_for('results'))
    
    # GET request - show the question
    if 1 <= question_id <= len(quiz_data['questions']):
        question = quiz_data['questions'][question_id - 1]
        
        # Get the user's previous answer for this question if it exists
        previous_answer = QuizAnswer.query.filter_by(
            question_id=question_id,
            quiz_session=session['quiz_session']
        ).first()
        
        app.logger.info(f'Question {question_id} displayed')
        return render_template('quiz.html', 
                             question=question,
                             current_question=question_id,
                             total_questions=len(quiz_data['questions']),
                             previous_answer=previous_answer.answer if previous_answer else None)
    
    app.logger.warning(f'Invalid question_id accessed: {question_id}')
    return redirect(url_for('index'))

@app.route('/results')
def results():
    # Check if there's an active quiz session
    if 'quiz_session' not in session:
        app.logger.warning('Results accessed without active session')
        return redirect(url_for('index'))
        
    # Get answers only from the current quiz session
    answers = QuizAnswer.query.filter_by(quiz_session=session['quiz_session'])\
                            .order_by(QuizAnswer.question_id)\
                            .all()
    
    # Calculate score based on current session only
    correct_answers = sum(1 for answer in answers if answer.is_correct)
    total_questions = len(quiz_data['questions'])
    score = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
    
    app.logger.info(f'Quiz completed with score: {score}%')
    
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
    app.run(debug=True) 