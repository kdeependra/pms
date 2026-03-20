"""
AI-powered Sentiment Analysis and Stakeholder Feedback Service
Handles sentiment analysis, text mining, action item generation, and satisfaction tracking
"""

import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from collections import Counter
import logging

# NLP Libraries
try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    from sentence_transformers import SentenceTransformer
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("Warning: Transformers not available. Install with: pip install transformers sentence-transformers torch")

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    print("Warning: spaCy not available. Install with: pip install spacy")

try:
    from nltk.tokenize import sent_tokenize, word_tokenize
    from nltk.corpus import stopwords
    from nltk.sentiment import SentimentIntensityAnalyzer
    import nltk
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt')
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False
    print("Warning: NLTK not available. Install with: pip install nltk")

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("Warning: scikit-learn not available. Install with: pip install scikit-learn")

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """AI-powered sentiment analysis using multiple NLP models"""
    
    def __init__(self):
        self.sentiment_pipeline = None
        self.zero_shot_pipeline = None
        self.embedding_model = None
        self.sia = None  # VADER sentiment analyzer
        self.nlp = None  # spaCy model
        self.action_keywords = self._build_action_keywords()
        
        self._initialize_models()
    
    def _initialize_models(self):
        """Initialize all available NLP models"""
        if TRANSFORMERS_AVAILABLE:
            try:
                # Sentiment analysis pipeline (distilbert-base-uncased-finetuned-sst-2-english)
                self.sentiment_pipeline = pipeline(
                    "sentiment-analysis",
                    model="distilbert-base-uncased-finetuned-sst-2-english"
                )
                logger.info("✓ Sentiment analysis pipeline loaded")
            except Exception as e:
                logger.warning(f"Failed to load sentiment pipeline: {e}")
            
            try:
                # Zero-shot classification for feedback categorization
                self.zero_shot_pipeline = pipeline(
                    "zero-shot-classification",
                    model="facebook/bart-large-mnli"
                )
                logger.info("✓ Zero-shot classification pipeline loaded")
            except Exception as e:
                logger.warning(f"Failed to load zero-shot pipeline: {e}")
            
            try:
                # Sentence embeddings for semantic similarity
                self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("✓ Embedding model loaded")
            except Exception as e:
                logger.warning(f"Failed to load embedding model: {e}")
        
        if NLTK_AVAILABLE:
            try:
                self.sia = SentimentIntensityAnalyzer()
                logger.info("✓ VADER sentiment analyzer loaded")
            except Exception as e:
                logger.warning(f"Failed to load VADER: {e}")
        
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load("en_core_web_sm")
                logger.info("✓ spaCy model loaded")
            except:
                logger.warning("spaCy model not found. Run: python -m spacy download en_core_web_sm")
    
    def _build_action_keywords(self) -> Dict[str, List[str]]:
        """Build keywords for action item detection"""
        return {
            'action': ['need to', 'should', 'must', 'will', 'action item', 'todo', 'task', 
                      'implement', 'fix', 'improve', 'add', 'create', 'develop', 'update'],
            'urgency': ['urgent', 'critical', 'asap', 'immediately', 'priority', 'high priority',
                       'critical path', 'blocker', 'showstopper'],
            'responsibility': ['responsible', 'owner', 'owner of', 'assigned to', 'to be done by',
                             'handled by', 'managed by', 'led by'],
            'timeline': ['by', 'within', 'before', 'after', 'by end of', 'by next', 'week',
                        'month', 'day', 'sprint', 'deadline']
        }
    
    def analyze_sentiment(self, text: str) -> Dict:
        """
        Analyze sentiment of text using multiple approaches
        Returns sentiment score (-1.0 to 1.0) and category
        """
        if not text or len(text.strip()) == 0:
            return {
                'sentiment_score': 0.0,
                'sentiment_category': 'neutral',
                'confidence': 0.0,
                'methods': {}
            }
        
        results = {
            'sentiment_score': 0.0,
            'sentiment_category': 'neutral',
            'confidence': 0.0,
            'methods': {}
        }
        
        scores = []
        
        # Method 1: Transformers
        if self.sentiment_pipeline:
            try:
                result = self.sentiment_pipeline(text[:512])[0]  # Max 512 tokens
                # Convert to -1.0 to 1.0 scale
                score = 1.0 if result['label'] == 'POSITIVE' else -1.0
                score *= result['score']
                scores.append(score)
                results['methods']['transformers'] = {
                    'label': result['label'],
                    'score': result['score'],
                    'normalized_score': score
                }
            except Exception as e:
                logger.warning(f"Transformers sentiment failed: {e}")
        
        # Method 2: VADER
        if self.sia:
            try:
                vader_scores = self.sia.polarity_scores(text)
                # Convert compound score from [-1, 1] to our scale
                score = vader_scores['compound']
                scores.append(score)
                results['methods']['vader'] = vader_scores
            except Exception as e:
                logger.warning(f"VADER sentiment failed: {e}")
        
        # Average the scores
        if scores:
            results['sentiment_score'] = float(np.mean(scores))
            results['confidence'] = float(np.std(scores)) if len(scores) > 1 else 0.9
        else:
            results['sentiment_score'] = 0.0
            results['confidence'] = 0.0
        
        # Categorize sentiment
        score = results['sentiment_score']
        if score > 0.5:
            results['sentiment_category'] = 'very_positive'
        elif score > 0.1:
            results['sentiment_category'] = 'positive'
        elif score < -0.5:
            results['sentiment_category'] = 'very_negative'
        elif score < -0.1:
            results['sentiment_category'] = 'negative'
        else:
            results['sentiment_category'] = 'neutral'
        
        return results
    
    def extract_key_topics(self, texts: List[str], num_topics: int = 5) -> List[Dict]:
        """Extract key topics from a list of texts using TF-IDF"""
        if not texts or not SKLEARN_AVAILABLE:
            return []
        
        try:
            # Remove short texts
            texts = [t for t in texts if len(t.split()) > 3]
            if not texts:
                return []
            
            vectorizer = TfidfVectorizer(max_features=100, stop_words='english')
            tfidf_matrix = vectorizer.fit_transform(texts)
            
            # Get feature names
            feature_names = vectorizer.get_feature_names_out()
            
            # Get top TF-IDF scores
            scores = np.asarray(tfidf_matrix.mean(axis=0)).ravel()
            top_indices = scores.argsort()[-num_topics:][::-1]
            
            topics = [
                {
                    'topic': feature_names[i],
                    'score': float(scores[i]),
                    'rank': rank + 1
                }
                for rank, i in enumerate(top_indices)
            ]
            
            return topics
        except Exception as e:
            logger.warning(f"Topic extraction failed: {e}")
            return []
    
    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract named entities from text"""
        if not self.nlp:
            return {'entities': [], 'entity_types': {}}
        
        try:
            doc = self.nlp(text)
            entities = [ent.text for ent in doc.ents]
            entity_types = {}
            for ent in doc.ents:
                if ent.label_ not in entity_types:
                    entity_types[ent.label_] = []
                entity_types[ent.label_].append(ent.text)
            
            return {
                'entities': list(set(entities)),
                'entity_types': entity_types
            }
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return {'entities': [], 'entity_types': {}}
    
    def generate_action_items(self, text: str) -> List[Dict]:
        """
        Extract action items from feedback text
        Uses keyword matching and sentence analysis
        """
        action_items = []
        
        try:
            # Sentence tokenization
            sentences = text.split('.')
            if not NLTK_AVAILABLE:
                sentences = text.split('.')
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                # Check for action keywords
                is_action = False
                for keyword in self.action_keywords['action']:
                    if keyword.lower() in sentence.lower():
                        is_action = True
                        break
                
                if is_action and len(sentence) > 10:
                    # Extract urgency
                    urgency = 'medium'
                    for urgent_keyword in self.action_keywords['urgency']:
                        if urgent_keyword.lower() in sentence.lower():
                            urgency = 'high'
                            break
                    
                    # Extract responsible party
                    responsible = None
                    for resp_keyword in self.action_keywords['responsibility']:
                        if resp_keyword.lower() in sentence.lower():
                            # Try to extract name after keyword
                            pattern = f"{resp_keyword}\\s+([A-Z][a-z]+\\s[A-Z][a-z]+)"
                            matches = re.finditer(pattern, sentence, re.IGNORECASE)
                            for match in matches:
                                responsible = match.group(1)
                                break
                            break
                    
                    # Extract timeline
                    timeline = None
                    for timeline_keyword in self.action_keywords['timeline']:
                        if timeline_keyword.lower() in sentence.lower():
                            timeline = timeline_keyword
                            break
                    
                    action_items.append({
                        'title': sentence,
                        'urgency': urgency,
                        'responsible': responsible,
                        'timeline': timeline,
                        'confidence': 0.7 if responsible else 0.5
                    })
        except Exception as e:
            logger.warning(f"Action item generation failed: {e}")
        
        return action_items
    
    def calculate_nps_score(self, ratings: List[int]) -> int:
        """
        Calculate Net Promoter Score (NPS)
        Ratings should be 0-10 scale
        NPS = % Promoters - % Detractors
        """
        if not ratings or len(ratings) == 0:
            return 0
        
        ratings = [r for r in ratings if 0 <= r <= 10]
        if not ratings:
            return 0
        
        promoters = len([r for r in ratings if r >= 9])
        detractors = len([r for r in ratings if r <= 6])
        passives = len([r for r in ratings if 7 <= r <= 8])
        
        total = len(ratings)
        nps = int(((promoters - detractors) / total) * 100)
        
        return nps
    
    def categorize_feedback(self, text: str, 
                          categories: Optional[List[str]] = None) -> Dict:
        """Categorize feedback using zero-shot classification"""
        if not self.zero_shot_pipeline or not text:
            return {
                'category': 'general',
                'confidence': 0.0,
                'scores': {}
            }
        
        if not categories:
            categories = ['positive feedback', 'negative feedback', 'suggestion', 
                         'bug report', 'feature request', 'general feedback']
        
        try:
            result = self.zero_shot_pipeline(text[:512], categories)
            return {
                'category': result['labels'][0],
                'confidence': float(result['scores'][0]),
                'scores': {label: float(score) 
                          for label, score in zip(result['labels'], result['scores'])}
            }
        except Exception as e:
            logger.warning(f"Feedback categorization failed: {e}")
            return {
                'category': 'general',
                'confidence': 0.0,
                'scores': {}
            }


class SurveyAnalyzer:
    """Analyzes survey responses and generates insights"""
    
    def __init__(self):
        self.sentiment_analyzer = SentimentAnalyzer()
    
    def analyze_survey_responses(self, responses: List[Dict]) -> Dict:
        """
        Analyze survey responses and generate comprehensive insights
        """
        if not responses:
            return self._empty_analysis()
        
        sentiment_scores = []
        sentiment_categories = Counter()
        all_feedback = []
        ratings = []
        
        for response in responses:
            if 'feedback_text' in response and response['feedback_text']:
                feedback = response['feedback_text']
                all_feedback.append(feedback)
                
                # Analyze sentiment
                sentiment = self.sentiment_analyzer.analyze_sentiment(feedback)
                sentiment_scores.append(sentiment['sentiment_score'])
                sentiment_categories[sentiment['sentiment_category']] += 1
            
            if 'rating' in response:
                try:
                    ratings.append(float(response['rating']))
                except:
                    pass
        
        # Calculate metrics
        total_responses = len(responses)
        avg_rating = float(np.mean(ratings)) if ratings else 0.0
        avg_sentiment = float(np.mean(sentiment_scores)) if sentiment_scores else 0.0
        
        # Calculate percentages
        total_sentiments = sum(sentiment_categories.values())
        sentiment_percentages = {
            cat: (count / total_sentiments * 100) if total_sentiments > 0 else 0
            for cat, count in sentiment_categories.items()
        }
        
        # Extract top topics
        top_topics = self.sentiment_analyzer.extract_key_topics(all_feedback, num_topics=5)
        
        # Generate action items from feedback
        action_items = []
        for feedback in all_feedback:
            items = self.sentiment_analyzer.generate_action_items(feedback)
            action_items.extend(items)
        
        # Calculate NPS if we have 0-10 ratings
        nps_score = 0
        if all([0 <= r <= 10 for r in ratings]):
            nps_score = self.sentiment_analyzer.calculate_nps_score(ratings)
        
        return {
            'total_responses': total_responses,
            'avg_rating': avg_rating,
            'avg_sentiment_score': avg_sentiment,
            'sentiment_distribution': dict(sentiment_percentages),
            'nps_score': nps_score,
            'top_topics': top_topics,
            'action_items': action_items[:10],  # Top 10 action items
            'response_rate': 0.0,  # To be calculated by caller
            'category_breakdown': {}
        }
    
    def _empty_analysis(self) -> Dict:
        """Return empty analysis structure"""
        return {
            'total_responses': 0,
            'avg_rating': 0.0,
            'avg_sentiment_score': 0.0,
            'sentiment_distribution': {
                'positive': 0, 'negative': 0, 'neutral': 0
            },
            'nps_score': 0,
            'top_topics': [],
            'action_items': [],
            'response_rate': 0.0,
            'category_breakdown': {}
        }
    
    def analyze_satisfaction_trend(self, satisfaction_records: List[Dict], 
                                  days: int = 30) -> Dict:
        """Analyze satisfaction trends over time"""
        if not satisfaction_records:
            return {'trend': 'stable', 'direction': 0, 'data': []}
        
        try:
            # Filter by date
            cutoff_date = datetime.now() - timedelta(days=days)
            recent_records = [
                r for r in satisfaction_records
                if r.get('timestamp', datetime.now()) > cutoff_date
            ]
            
            if not recent_records:
                return {'trend': 'stable', 'direction': 0, 'data': []}
            
            # Group by date and calculate daily average
            daily_data = {}
            for record in recent_records:
                date_key = record.get('timestamp', datetime.now()).date()
                if date_key not in daily_data:
                    daily_data[date_key] = []
                daily_data[date_key].append(record.get('score', 0))
            
            # Calculate trend
            sorted_dates = sorted(daily_data.keys())
            if len(sorted_dates) < 2:
                return {'trend': 'stable', 'direction': 0, 'data': []}
            
            early_avg = np.mean(daily_data[sorted_dates[0]])
            recent_avg = np.mean(daily_data[sorted_dates[-1]])
            direction = recent_avg - early_avg
            
            if direction > 0.3:
                trend = 'improving'
            elif direction < -0.3:
                trend = 'declining'
            else:
                trend = 'stable'
            
            # Build data array
            data = [
                {'date': str(date), 'avg_score': float(np.mean(daily_data[date]))}
                for date in sorted_dates
            ]
            
            return {
                'trend': trend,
                'direction': float(direction),
                'data': data
            }
        except Exception as e:
            logger.warning(f"Satisfaction trend analysis failed: {e}")
            return {'trend': 'stable', 'direction': 0, 'data': []}


# Global instances
sentiment_analyzer = SentimentAnalyzer()
survey_analyzer = SurveyAnalyzer()
