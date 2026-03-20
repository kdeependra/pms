import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from datetime import datetime, timedelta
import pickle
import os

class TimelinePredictor:
    """ML model for predicting project completion timelines"""
    
    def __init__(self, model_path="./models/timeline_model.pkl"):
        self.model_path = model_path
        self.model = None
        self.load_model()
    
    def load_model(self):
        """Load pre-trained model or create new one"""
        if os.path.exists(self.model_path):
            with open(self.model_path, 'rb') as f:
                self.model = pickle.load(f)
        else:
            self.model = RandomForestRegressor(n_estimators=100, random_state=42)
    
    def train(self, historical_data):
        """Train the model on historical project data"""
        # Features: project_size, team_size, complexity, budget
        # Target: actual_duration_days
        
        X = historical_data[['project_size', 'team_size', 'complexity', 'budget']]
        y = historical_data['actual_duration_days']
        
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        self.model.fit(X_train, y_train)
        score = self.model.score(X_test, y_test)
        
        # Save model
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        with open(self.model_path, 'wb') as f:
            pickle.dump(self.model, f)
        
        return score
    
    def predict(self, project_features):
        """Predict project completion timeline"""
        # project_features: dict with keys: project_size, team_size, complexity, budget
        features = np.array([[
            project_features['project_size'],
            project_features['team_size'],
            project_features['complexity'],
            project_features['budget']
        ]])
        
        predicted_days = self.model.predict(features)[0]
        predicted_date = datetime.now() + timedelta(days=int(predicted_days))
        
        # Calculate confidence based on feature importance
        confidence = 0.85  # Simplified, should be based on model uncertainty
        
        return {
            'predicted_completion_date': predicted_date,
            'predicted_duration_days': int(predicted_days),
            'confidence_score': confidence
        }

class RiskPredictor:
    """ML model for predicting project risks"""
    
    def __init__(self):
        self.risk_categories = [
            'scope_creep',
            'resource_shortage',
            'technical_debt',
            'stakeholder_conflict',
            'budget_overrun'
        ]
    
    def predict_risks(self, project_data):
        """Predict potential risks for a project"""
        # Simplified rule-based prediction (replace with ML model)
        risks = []
        
        # Check for scope creep risk
        if project_data.get('requirements_changes', 0) > 5:
            risks.append({
                'risk': 'scope_creep',
                'probability': 0.7,
                'impact': 'high',
                'description': 'High number of requirement changes detected'
            })
        
        # Check for resource shortage
        if project_data.get('team_utilization', 0) > 90:
            risks.append({
                'risk': 'resource_shortage',
                'probability': 0.65,
                'impact': 'high',
                'description': 'Team operating at >90% capacity'
            })
        
        # Check for budget overrun
        if project_data.get('burn_rate', 0) > project_data.get('planned_burn_rate', 0) * 1.2:
            risks.append({
                'risk': 'budget_overrun',
                'probability': 0.8,
                'impact': 'critical',
                'description': 'Burn rate 20% higher than planned'
            })
        
        return risks

class ResourceOptimizer:
    """ML-based resource allocation optimizer"""
    
    def optimize_allocation(self, resources, tasks):
        """Optimize resource allocation across tasks"""
        # Simplified optimization (replace with LP/ML approach)
        recommendations = []
        
        for resource in resources:
            if resource['utilization'] > 100:
                recommendations.append({
                    'type': 'overallocation',
                    'resource_id': resource['id'],
                    'current_utilization': resource['utilization'],
                    'suggestion': f"Reassign tasks to reduce load by {resource['utilization'] - 100}%"
                })
            elif resource['utilization'] < 50:
                recommendations.append({
                    'type': 'underutilization',
                    'resource_id': resource['id'],
                    'current_utilization': resource['utilization'],
                    'suggestion': f"Assign additional tasks to utilize {100 - resource['utilization']}% capacity"
                })
        
        return recommendations

# Example usage
if __name__ == "__main__":
    # Timeline prediction
    predictor = TimelinePredictor()
    result = predictor.predict({
        'project_size': 100,  # story points
        'team_size': 5,
        'complexity': 7,  # 1-10 scale
        'budget': 500000
    })
    print("Timeline Prediction:", result)
    
    # Risk prediction
    risk_predictor = RiskPredictor()
    risks = risk_predictor.predict_risks({
        'requirements_changes': 8,
        'team_utilization': 95,
        'burn_rate': 15000,
        'planned_burn_rate': 12000
    })
    print("Predicted Risks:", risks)
