"""
Phase 5: What-If Scenario Planning - Scenario Simulation Service

Provides Monte Carlo simulations, sensitivity analysis, and scenario comparison.
Calculates probability distributions and risk metrics for project scenarios.
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import json
from scipy import stats
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# ============ DATA STRUCTURES ============

@dataclass
class SimulationParameter:
    """Parameters for a simulation variable"""
    name: str
    baseline_value: float
    scenario_value: float
    min_value: float = None
    max_value: float = None
    distribution_type: str = "normal"  # normal, uniform, triangular, lognormal
    
    def to_dict(self):
        return {
            'name': self.name,
            'baseline_value': self.baseline_value,
            'scenario_value': self.scenario_value,
            'min_value': self.min_value,
            'max_value': self.max_value,
            'distribution_type': self.distribution_type,
        }


@dataclass
class SimulationResult:
    """Results from Monte Carlo simulation"""
    expected_value: float
    best_case: float
    worst_case: float
    confidence_interval_95: float
    probability_success: float
    distribution: List[float]
    percentiles: Dict[int, float]
    std_deviation: float


# ============ MONTE CARLO SIMULATOR ============

class MonteCarloSimulator:
    """Performs Monte Carlo simulations for project scenarios"""
    
    ITERATIONS_DEFAULT = 1000
    SEED = 42
    
    def __init__(self, iterations: int = ITERATIONS_DEFAULT):
        """Initialize simulator with number of iterations"""
        self.iterations = iterations
        np.random.seed(self.SEED)
    
    # ============ DISTRIBUTION GENERATORS ============
    
    def generate_normal_distribution(self, 
                                     mean: float, 
                                     std: float,
                                     size: int) -> np.ndarray:
        """Generate normal distribution samples"""
        return np.random.normal(mean, std, size)
    
    def generate_uniform_distribution(self, 
                                      low: float, 
                                      high: float,
                                      size: int) -> np.ndarray:
        """Generate uniform distribution samples"""
        return np.random.uniform(low, high, size)
    
    def generate_triangular_distribution(self, 
                                        low: float, 
                                        mode: float, 
                                        high: float,
                                        size: int) -> np.ndarray:
        """Generate triangular distribution samples (best, likely, worst cases)"""
        return np.random.triangular(low, mode, high, size)
    
    def generate_lognormal_distribution(self, 
                                       mean: float, 
                                       std: float,
                                       size: int) -> np.ndarray:
        """Generate lognormal distribution (for positive values like costs)"""
        sigma = np.sqrt(np.log(1 + (std / mean) ** 2))
        mu = np.log(mean) - sigma ** 2 / 2
        return np.random.lognormal(mu, sigma, size)
    
    def get_samples(self, 
                   baseline: float, 
                   scenario: float, 
                   distribution_type: str = "normal",
                   min_val: float = None,
                   max_val: float = None) -> np.ndarray:
        """Get distribution samples based on type"""
        if distribution_type == "normal":
            std = abs(scenario - baseline) * 0.3  # Assume 30% std dev
            return self.generate_normal_distribution(scenario, std, self.iterations)
        
        elif distribution_type == "uniform":
            low = min_val if min_val else min(baseline, scenario) * 0.5
            high = max_val if max_val else max(baseline, scenario) * 1.5
            return self.generate_uniform_distribution(low, high, self.iterations)
        
        elif distribution_type == "triangular":
            low = min_val if min_val else scenario * 0.7
            high = max_val if max_val else scenario * 1.3
            mode = scenario
            return self.generate_triangular_distribution(low, mode, high, self.iterations)
        
        elif distribution_type == "lognormal":
            std = abs(scenario - baseline)
            return self.generate_lognormal_distribution(scenario, std, self.iterations)
        
        else:
            return self.generate_normal_distribution(scenario, abs(scenario - baseline) * 0.3, self.iterations)
    
    # ============ SIMULATION EXECUTION ============
    
    def simulate_timeline(self, 
                         baseline_timeline: float,
                         scope_change: float,
                         resource_change: float,
                         quality_focus: float) -> SimulationResult:
        """
        Simulate project timeline under scenario
        
        Args:
            baseline_timeline: Original timeline in days
            scope_change: % change in scope (1.0 = no change, 1.2 = +20%)
            resource_change: % change in resources
            quality_focus: Quality priority (0.5-1.5, affects productivity)
        
        Returns:
            SimulationResult with timeline statistics
        """
        # Generate scenarios for timeline impact
        scope_impact = self.get_samples(baseline_timeline, baseline_timeline * scope_change)
        resource_impact = self.get_samples(baseline_timeline, baseline_timeline * (1 / resource_change))
        
        # Combined impact: scope increases time, resources reduce it
        combined_timeline = scope_impact * (1 / resource_impact) * quality_focus
        
        return self._create_result(combined_timeline, baseline_timeline)
    
    def simulate_budget(self, 
                       baseline_budget: float,
                       scope_change: float,
                       hourly_rate_change: float,
                       resource_change: float,
                       inflation: float = 0.02) -> SimulationResult:
        """
        Simulate project budget under scenario
        
        Args:
            baseline_budget: Original budget in dollars
            scope_change: % change in scope
            hourly_rate_change: % change in rates
            resource_change: % change in team size
            inflation: Annual inflation rate
        """
        # Generate budget impact factors
        scope_factor = self.get_samples(1.0, scope_change, "triangular")
        rate_factor = self.get_samples(1.0, hourly_rate_change, "lognormal")
        resource_factor = self.get_samples(1.0, resource_change, "normal")
        
        # Combined budget = baseline * scope * rate * resources * inflation
        combined_budget = baseline_budget * scope_factor * rate_factor * resource_factor * (1 + inflation)
        
        return self._create_result(combined_budget, baseline_budget)
    
    def simulate_resource_demand(self, 
                                baseline_team_size: int,
                                resource_change: float) -> SimulationResult:
        """Simulate required team size changes"""
        demand = self.get_samples(baseline_team_size, 
                                 int(baseline_team_size * resource_change),
                                 "triangular",
                                 min_val=max(1, baseline_team_size * 0.5),
                                 max_val=baseline_team_size * 2.0)
        return self._create_result(demand, baseline_team_size)
    
    def simulate_quality_score(self, 
                              baseline_quality: float,
                              resource_change: float,
                              timeline_pressure: float) -> SimulationResult:
        """
        Simulate quality under scenario
        
        Quality inversely affected by timeline pressure and resource constraints
        """
        # More resources improve quality, tight timeline reduces it
        quality_factor = (resource_change * 0.5) + (1 / timeline_pressure * 0.5)
        adjusted_quality = baseline_quality * quality_factor
        
        samples = self.get_samples(baseline_quality, adjusted_quality, "normal",
                                  min_val=0, max_val=100)
        
        return self._create_result(samples, baseline_quality)
    
    # ============ RISK ANALYSIS ============
    
    def calculate_risk_probability(self, 
                                  actual_value: float,
                                  threshold: float,
                                  distribution: np.ndarray) -> float:
        """
        Calculate probability of exceeding/falling below threshold
        
        Args:
            actual_value: Current value
            threshold: Target threshold
            distribution: Array of simulated values
        """
        if threshold > actual_value:
            # Probability of exceeding (worst case)
            probability = np.sum(distribution >= threshold) / len(distribution)
        else:
            # Probability of not reaching (falling below)
            probability = np.sum(distribution < threshold) / len(distribution)
        
        return float(min(1.0, max(0.0, probability)))
    
    def identify_critical_risks(self, 
                               variable_distributions: Dict[str, np.ndarray],
                               thresholds: Dict[str, float],
                               confidence_level: float = 0.95) -> List[Dict]:
        """
        Identify risks at specified confidence level
        
        Args:
            variable_distributions: Dict of variable_name -> distribution array
            thresholds: Dict of variable_name -> threshold value
            confidence_level: Confidence level (0-1)
        """
        critical_risks = []
        
        for var_name, distribution in variable_distributions.items():
            threshold = thresholds.get(var_name)
            if threshold is None:
                continue
            
            # Calculate if there's significant risk
            percentile = int((1 - confidence_level) * 100)
            lower_bound = np.percentile(distribution, percentile)
            
            if lower_bound < threshold:
                risk_prob = self.calculate_risk_probability(np.mean(distribution), 
                                                            threshold, 
                                                            distribution)
                
                critical_risks.append({
                    'variable': var_name,
                    'threshold': threshold,
                    'expected_value': float(np.mean(distribution)),
                    'lower_bound': float(lower_bound),
                    'risk_probability': risk_prob,
                    'severity': 'critical' if risk_prob > 0.3 else 'medium' if risk_prob > 0.1 else 'low',
                })
        
        return sorted(critical_risks, key=lambda x: x['risk_probability'], reverse=True)
    
    # ============ HELPER METHODS ============
    
    def _create_result(self, samples: np.ndarray, baseline: float) -> SimulationResult:
        """Create SimulationResult from sampled data"""
        samples = np.clip(samples, 0, samples.max())  # Remove negative values
        
        return SimulationResult(
            expected_value=float(np.mean(samples)),
            best_case=float(np.percentile(samples, 10)),
            worst_case=float(np.percentile(samples, 90)),
            confidence_interval_95=float(np.percentile(samples, 97.5) - np.percentile(samples, 2.5)),
            probability_success=self._calculate_success_probability(samples, baseline),
            distribution=samples.tolist(),
            percentiles={
                10: float(np.percentile(samples, 10)),
                25: float(np.percentile(samples, 25)),
                50: float(np.percentile(samples, 50)),
                75: float(np.percentile(samples, 75)),
                90: float(np.percentile(samples, 90)),
            },
            std_deviation=float(np.std(samples)),
        )
    
    def _calculate_success_probability(self, samples: np.ndarray, baseline: float) -> float:
        """Calculate probability of meeting baseline"""
        success = np.sum(samples <= baseline * 1.1) / len(samples)  # Within 10% of baseline
        return float(min(1.0, max(0.0, success)))


# ============ SENSITIVITY ANALYSIS ============

class SensitivityAnalyzer:
    """Performs sensitivity analysis to identify critical variables"""
    
    def __init__(self, simulator: MonteCarloSimulator):
        """Initialize with a Monte Carlo simulator"""
        self.simulator = simulator
    
    def tornado_analysis(self, 
                        baseline: Dict[str, float],
                        scenario: Dict[str, float],
                        target_metric_function,
                        interval_percent: float = 0.1) -> List[Dict]:
        """
        Tornado diagram analysis - shows which variables have highest impact
        
        Args:
            baseline: Dict of variable values at baseline
            scenario: Dict of variable values in scenario
            target_metric_function: Function to calculate target metric
            interval_percent: Percentage to vary each variable
        
        Returns:
            Sorted list of variable impacts
        """
        impacts = []
        
        # Calculate baseline metric
        baseline_metric = target_metric_function(baseline)
        
        for var_name, baseline_val in baseline.items():
            if baseline_val == 0:
                continue
            
            # Low case: reduce variable by interval
            low_vars = baseline.copy()
            low_vars[var_name] = baseline_val * (1 - interval_percent)
            low_metric = target_metric_function(low_vars)
            
            # High case: increase variable by interval
            high_vars = baseline.copy()
            high_vars[var_name] = baseline_val * (1 + interval_percent)
            high_metric = target_metric_function(high_vars)
            
            # Calculate tornado contribution
            tornado_range = abs(high_metric - low_metric)
            
            impacts.append({
                'variable': var_name,
                'baseline_value': baseline_val,
                'scenario_value': scenario.get(var_name, baseline_val),
                'low_case': low_metric,
                'high_case': high_metric,
                'tornado_range': tornado_range,
                'elasticity': (tornado_range / baseline_metric) / (2 * interval_percent),
                'importance_rank': 0,  # Will be set after sorting
            })
        
        # Sort by tornado range (descending)
        impacts.sort(key=lambda x: x['tornado_range'], reverse=True)
        
        # Assign importance ranks
        for i, impact in enumerate(impacts, 1):
            impact['importance_rank'] = i
            impact['variance_contributed'] = (impact['tornado_range'] / sum(i['tornado_range'] for i in impacts)) * 100
        
        return impacts
    
    def one_way_sensitivity(self, 
                           variable_name: str,
                           baseline_value: float,
                           range_percent: float,
                           steps: int,
                           calculation_function) -> Dict:
        """
        One-way sensitivity analysis - how output changes with one variable
        
        Args:
            variable_name: Name of variable to vary
            baseline_value: Current value
            range_percent: Range to test (e.g., 0.2 = ±20%)
            steps: Number of steps to test
            calculation_function: Function that takes value and returns metric
        """
        low_value = baseline_value * (1 - range_percent)
        high_value = baseline_value * (1 + range_percent)
        
        values = np.linspace(low_value, high_value, steps)
        metrics = [calculation_function(val) for val in values]
        
        # Calculate elasticity at baseline
        baseline_metric = calculation_function(baseline_value)
        elasticity = (metrics[-1] - metrics[0]) / (high_value - low_value) / baseline_metric
        
        return {
            'variable': variable_name,
            'baseline_value': baseline_value,
            'range': (float(low_value), float(high_value)),
            'values': values.tolist(),
            'metrics': metrics,
            'elasticity': float(elasticity),
            'correlation_coefficient': float(np.corrcoef(values, metrics)[0, 1]),
        }
    
    def pareto_analysis(self, variable_impacts: List[Dict]) -> Dict:
        """
        Pareto analysis - identify 20% of variables causing 80% of variance
        
        Returns dict with critical and non-critical variables
        """
        total_variance = sum(v['variance_contributed'] for v in variable_impacts)
        
        cumulative = 0
        critical_variables = []
        
        for impact in variable_impacts:
            cumulative += impact['variance_contributed']
            critical_variables.append(impact)
            if cumulative >= 80:
                break
        
        non_critical = variable_impacts[len(critical_variables):]
        
        return {
            'critical_variables': critical_variables,
            'non_critical_variables': non_critical,
            'critical_count': len(critical_variables),
            'non_critical_count': len(non_critical),
            'variance_explained': cumulative,
        }


# ============ SCENARIO COMPARISON ============

class ScenarioComparator:
    """Compares multiple scenarios"""
    
    def __init__(self, simulator: MonteCarloSimulator, analyzer: SensitivityAnalyzer):
        """Initialize with simulator and analyzer"""
        self.simulator = simulator
        self.analyzer = analyzer
    
    def compare_scenarios(self, 
                         scenarios: List[Dict]) -> Dict:
        """
        Compare multiple scenarios
        
        Args:
            scenarios: List of scenario dicts with simulation results
        
        Returns:
            Comparison results with recommendations
        """
        comparison = {
            'scenario_count': len(scenarios),
            'scenarios': [],
            'metrics_comparison': {},
            'winner': None,
            'recommendations': [],
        }
        
        # Score each scenario
        scenario_scores = []
        metrics_by_scenario = {}
        
        for i, scenario in enumerate(scenarios):
            score = self._score_scenario(scenario)
            scenario_scores.append((i, score, scenario['name']))
            
            # Extract metrics
            metrics = {
                'timeline_expected': scenario.get('expected_timeline', 0),
                'budget_expected': scenario.get('expected_budget', 0),
                'risk_score': scenario.get('overall_risk_score', 50),
                'quality_expected': scenario.get('expected_quality_score', 50),
            }
            metrics_by_scenario[i] = metrics
            
            comparison['scenarios'].append({
                'name': scenario['name'],
                'score': score,
                'metrics': metrics,
            })
        
        # Sort by score (highest = best)
        scenario_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Determine winner
        if scenario_scores:
            best_idx = scenario_scores[0][0]
            comparison['winner'] = scenarios[best_idx]['name']
            comparison['winner_reason'] = f"Best overall score: {scenario_scores[0][1]:.2f}"
        
        # Generate recommendations
        comparison['recommendations'] = self._generate_recommendations(scenarios, scenario_scores)
        
        return comparison
    
    def _score_scenario(self, scenario: Dict) -> float:
        """Calculate composite score for scenario"""
        timeline_component = max(0, 50 - abs(scenario.get('expected_timeline', 0) - scenario.get('baseline_timeline', 0)))
        budget_component = max(0, 50 - (scenario.get('expected_budget', 0) / scenario.get('baseline_budget', 1) * 100))
        risk_component = 100 - scenario.get('overall_risk_score', 50)
        quality_component = scenario.get('expected_quality_score', 50)
        
        return (timeline_component + budget_component + risk_component + quality_component) / 4
    
    def _generate_recommendations(self, scenarios: List[Dict], scores: List[Tuple]) -> List[str]:
        """Generate recommendations based on comparison"""
        recommendations = []
        
        if len(scores) > 1:
            best_score = scores[0][1]
            worst_score = scores[-1][1]
            
            if best_score - worst_score > 20:
                recommendations.append(f"Strong preference for best scenario: {formats:.1f} points better than worst")
            else:
                recommendations.append("Multiple viable scenarios - consider trade-offs")
        
        # Check for common risks
        risk_scores = [s.get('overall_risk_score', 50) for s in scenarios]
        if max(risk_scores) > 70:
            recommendations.append("High risk identified in several scenarios - requires mitigation planning")
        
        return recommendations
    
    def generate_comparison_table(self, scenarios: List[Dict]) -> List[Dict]:
        """Generate comparison table for display"""
        headers = ['Scenario', 'Timeline (days)', 'Budget ($)', 'Risk Score', 'Quality', 'Success Prob']
        
        rows = []
        for scenario in scenarios:
            rows.append({
                'scenario': scenario['name'],
                'timeline': f"{scenario.get('expected_timeline', 0):.1f}",
                'budget': f"${scenario.get('expected_budget', 0):,.0f}",
                'risk': f"{scenario.get('overall_risk_score', 50):.0f}",
                'quality': f"{scenario.get('expected_quality_score', 50):.0f}",
                'success': f"{scenario.get('timeline_probability_success', 0.5) * 100:.0f}%",
            })
        
        return rows


# ============ PROBABILITY DISTRIBUTION GENERATOR ============

class ProbabilityDistributionAnalyzer:
    """Analyzes and generates probability distributions"""
    
    @staticmethod
    def fit_distribution(data: np.ndarray) -> Dict:
        """
        Fit best-matching distribution to data
        
        Tests normal, lognormal, and triangular distributions
        """
        # Test different distributions
        distributions = {}
        
        # Normal distribution
        mu, sigma = stats.norm.fit(data)
        distributions['normal'] = {
            'params': {'mu': mu, 'sigma': sigma},
            'ks_statistic': float(stats.kstest(data, 'norm')[0]),
        }
        
        # Lognormal distribution
        if np.all(data > 0):
            shape, loc, scale = stats.lognorm.fit(data)
            distributions['lognormal'] = {
                'params': {'shape': shape, 'loc': loc, 'scale': scale},
                'ks_statistic': float(stats.kstest(data, 'lognorm')[0]),
            }
        
        # Find best fit (lowest KS statistic)
        best_fit = min(distributions.items(), key=lambda x: x[1]['ks_statistic'])
        
        return {
            'best_fit': best_fit[0],
            'all_fits': distributions,
            'data_stats': {
                'mean': float(np.mean(data)),
                'median': float(np.median(data)),
                'std': float(np.std(data)),
                'min': float(np.min(data)),
                'max': float(np.max(data)),
                'skewness': float(stats.skew(data)),
                'kurtosis': float(stats.kurtosis(data)),
            }
        }
    
    @staticmethod
    def calculate_confidence_intervals(data: np.ndarray, 
                                      confidence: float = 0.95) -> Dict:
        """Calculate confidence intervals for data"""
        percentile_low = (1 - confidence) / 2 * 100
        percentile_high = (1 + confidence) / 2 * 100
        
        return {
            'confidence_level': confidence,
            'lower_bound': float(np.percentile(data, percentile_low)),
            'upper_bound': float(np.percentile(data, percentile_high)),
            'range': float(np.percentile(data, percentile_high) - np.percentile(data, percentile_low)),
            'mean': float(np.mean(data)),
            'median': float(np.median(data)),
        }


# ============ INTEGRATED SCENARIO ENGINE ============

class ScenarioEngine:
    """Main engine for managing WhatIf scenarios"""
    
    def __init__(self, iterations: int = 1000):
        """Initialize engines"""
        self.simulator = MonteCarloSimulator(iterations)
        self.analyzer = SensitivityAnalyzer(self.simulator)
        self.comparator = ScenarioComparator(self.simulator, self.analyzer)
    
    def create_scenario(self, 
                       project_data: Dict,
                       scenario_name: str,
                       variables: Dict[str, float]) -> Dict:
        """
        Create and analyze a WhatIf scenario
        
        Args:
            project_data: Current project baseline data
            scenario_name: Name of the scenario
            variables: Dictionary of variables to modify {var_name: multiplier}
        
        Returns:
            Complete scenario analysis
        """
        baseline_timeline = project_data.get('duration', 30)
        baseline_budget = project_data.get('budget', 100000)
        baseline_team = project_data.get('team_size', 5)
        baseline_quality = project_data.get('quality_target', 85)
        
        # Extract scenario parameters
        scope_change = variables.get('scope_multiplier', 1.0)
        resource_change = variables.get('resource_multiplier', 1.0)
        quality_focus = variables.get('quality_focus', 1.0)
        hourly_rate_change = variables.get('hourly_rate_multiplier', 1.0)
        
        # Run simulations
        timeline_result = self.simulator.simulate_timeline(
            baseline_timeline, scope_change, resource_change, quality_focus
        )
        
        budget_result = self.simulator.simulate_budget(
            baseline_budget, scope_change, hourly_rate_change, resource_change
        )
        
        resource_result = self.simulator.simulate_resource_demand(
            baseline_team, resource_change
        )
        
        quality_result = self.simulator.simulate_quality_score(
            baseline_quality, resource_change, scope_change
        )
        
        # Sensitivity analysis
        baseline_vars = {
            'scope': 1.0,
            'resources': 1.0,
            'quality_focus': 1.0,
            'hourly_rate': 1.0,
        }
        
        def cost_calculation(vars_dict):
            return baseline_budget * vars_dict.get('scope', 1.0) * vars_dict.get('hourly_rate', 1.0)
        
        sensitivity = self.analyzer.tornado_analysis(baseline_vars, variables, cost_calculation)
        
        # Overall risk score
        risks = self.simulator.identify_critical_risks(
            {
                'timeline': np.array(timeline_result.distribution),
                'budget': np.array(budget_result.distribution),
                'quality': np.array(quality_result.distribution),
            },
            {
                'timeline': baseline_timeline * 1.3,
                'budget': baseline_budget * 1.3,
                'quality': baseline_quality * 0.8,
            }
        )
        
        overall_risk_score = sum(r['risk_probability'] for r in risks) / 3 * 100
        
        return {
            'scenario_name': scenario_name,
            'variables': variables,
            'timeline': {
                'expected': timeline_result.expected_value,
                'best_case': timeline_result.best_case,
                'worst_case': timeline_result.worst_case,
                'percentiles': timeline_result.percentiles,
                'success_probability': timeline_result.probability_success,
                'distribution': timeline_result.distribution[:100],  # Sample for display
            },
            'budget': {
                'expected': budget_result.expected_value,
                'best_case': budget_result.best_case,
                'worst_case': budget_result.worst_case,
                'percentiles': budget_result.percentiles,
                'success_probability': budget_result.probability_success,
                'distribution': budget_result.distribution[:100],
            },
            'resources': {
                'expected': resource_result.expected_value,
                'best_case': resource_result.best_case,
                'worst_case': resource_result.worst_case,
                'percentiles': resource_result.percentiles,
            },
            'quality': {
                'expected': quality_result.expected_value,
                'best_case': quality_result.best_case,
                'worst_case': quality_result.worst_case,
                'percentiles': quality_result.percentiles,
            },
            'sensitivity_analysis': sensitivity,
            'critical_risks': risks,
            'overall_risk_score': overall_risk_score,
            'created_at': datetime.now().isoformat(),
        }
    
    def compare_scenarios(self, scenarios: List[Dict]) -> Dict:
        """Compare multiple scenarios"""
        return self.comparator.compare_scenarios(scenarios)
    
    def generate_comparison_table(self, scenarios: List[Dict]) -> List[Dict]:
        """Generate comparison table"""
        return self.comparator.generate_comparison_table(scenarios)
