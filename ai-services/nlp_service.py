import spacy
from transformers import pipeline
from typing import List, Dict
import re

class NLPProcessor:
    """Natural Language Processing for task extraction and meeting summaries"""
    
    def __init__(self):
        # Load spaCy model
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except:
            print("Warning: spaCy model not found. Run: python -m spacy download en_core_web_sm")
            self.nlp = None
        
        # Load summarization pipeline
        try:
            self.summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
        except:
            print("Warning: Summarization model not available")
            self.summarizer = None
    
    def extract_tasks_from_text(self, text: str) -> List[Dict]:
        """Extract action items/tasks from text"""
        if not self.nlp:
            return []
        
        doc = self.nlp(text)
        tasks = []
        
        # Pattern matching for task-like sentences
        task_patterns = [
            r'(?:TODO|To do|Action item|Task):\s*(.+)',
            r'(?:Need to|Should|Must|Will)\s+(.+)',
            r'(?:\[\s*\]|\[ \])\s*(.+)'  # Checkbox pattern
        ]
        
        for pattern in task_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                task_text = match.group(1).strip()
                
                # Extract entities (person, date, etc.)
                task_doc = self.nlp(task_text)
                assignee = None
                due_date = None
                
                for ent in task_doc.ents:
                    if ent.label_ == "PERSON":
                        assignee = ent.text
                    elif ent.label_ == "DATE":
                        due_date = ent.text
                
                tasks.append({
                    'title': task_text,
                    'assignee': assignee,
                    'due_date': due_date,
                    'source': 'nlp_extraction'
                })
        
        return tasks
    
    def summarize_meeting(self, transcript: str, max_length: int = 150) -> Dict:
        """Generate meeting summary from transcript"""
        if not self.summarizer or len(transcript) < 100:
            return {
                'summary': transcript[:200],
                'key_points': [],
                'action_items': []
            }
        
        # Generate summary
        summary = self.summarizer(
            transcript,
            max_length=max_length,
            min_length=50,
            do_sample=False
        )[0]['summary_text']
        
        # Extract key points (simplified)
        doc = self.nlp(transcript)
        sentences = [sent.text for sent in doc.sents]
        key_points = sentences[:3]  # Top 3 sentences as key points
        
        # Extract action items
        action_items = self.extract_tasks_from_text(transcript)
        
        return {
            'summary': summary,
            'key_points': key_points,
            'action_items': action_items
        }
    
    def analyze_sentiment(self, text: str) -> Dict:
        """Analyze sentiment of text (for team morale tracking)"""
        if not self.nlp:
            return {'sentiment': 'neutral', 'score': 0.5}
        
        # Simplified sentiment analysis
        # In production, use a proper sentiment model
        doc = self.nlp(text)
        
        positive_words = {'good', 'great', 'excellent', 'happy', 'successful', 'completed'}
        negative_words = {'bad', 'poor', 'problem', 'issue', 'delay', 'failed', 'blocked'}
        
        text_lower = text.lower()
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            sentiment = 'positive'
            score = 0.7
        elif negative_count > positive_count:
            sentiment = 'negative'
            score = 0.3
        else:
            sentiment = 'neutral'
            score = 0.5
        
        return {
            'sentiment': sentiment,
            'score': score,
            'positive_count': positive_count,
            'negative_count': negative_count
        }

class Chatbot:
    """AI-powered chatbot for project queries"""
    
    def __init__(self):
        self.nlp_processor = NLPProcessor()
        self.context = {}
    
    def process_query(self, query: str, user_context: Dict = None) -> str:
        """Process user query and generate response"""
        query_lower = query.lower()
        
        # Simple rule-based responses (replace with actual AI model)
        if 'status' in query_lower and 'project' in query_lower:
            return "Your project 'Website Redesign' is 65% complete and on track for delivery next month."
        
        elif 'task' in query_lower and ('create' in query_lower or 'add' in query_lower):
            return "I can help you create a task. Please provide the task details: title, assignee, and due date."
        
        elif 'overdue' in query_lower or 'late' in query_lower:
            return "You have 3 overdue tasks: 'Database Migration' (2 days overdue), 'API Integration' (1 day overdue), and 'Testing' (5 days overdue)."
        
        elif 'resource' in query_lower and 'utilization' in query_lower:
            return "Current team utilization: John (85%), Sarah (92%), Mike (78%), Lisa (95%). Lisa is near capacity."
        
        elif 'risk' in query_lower:
            return "Current project has 2 medium risks and 1 high risk. The high risk is 'Scope Creep' with 70% probability."
        
        elif 'help' in query_lower:
            return """I can help you with:
- Check project status
- Create/update tasks
- View overdue items
- Check resource utilization
- Analyze risks
- Generate reports
What would you like to do?"""
        
        else:
            return f"I'm processing your query: '{query}'. How else can I assist you with project management?"

# Example usage
if __name__ == "__main__":
    # NLP Processing
    nlp = NLPProcessor()
    
    sample_text = """
    Meeting Notes:
    - TODO: John needs to complete the database migration by Friday
    - Action item: Sarah will review the API documentation
    - We should schedule a demo with stakeholders next week
    - [ ] Mike to fix the login bug
    """
    
    tasks = nlp.extract_tasks_from_text(sample_text)
    print("Extracted Tasks:", tasks)
    
    # Chatbot
    bot = Chatbot()
    response = bot.process_query("What is the status of my project?")
    print("Chatbot Response:", response)
