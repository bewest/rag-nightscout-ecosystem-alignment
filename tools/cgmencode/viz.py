import matplotlib.pyplot as plt
import numpy as np
import torch

def plot_stochastic_forecast(history_glucose, future_samples, title="Physiological Forecast Cloud"):
    """
    Plots a 6-hour history and a 'cloud' of possible futures.
    history_glucose: 1D array of historical SGVs.
    future_samples: (NumSamples, SeqLen) array of predicted future SGVs.
    """
    plt.figure(figsize=(12, 6))
    
    # Time axes
    hist_len = len(history_glucose)
    fut_len = future_samples.shape[1]
    t_hist = np.arange(-hist_len, 0) * 5 # 5-min intervals
    t_fut = np.arange(0, fut_len) * 5
    
    # Plot History
    plt.plot(t_hist, history_glucose, color='black', linewidth=2, label='History')
    
    # Plot Stochastic Cloud
    for i in range(min(len(future_samples), 100)):
        plt.plot(t_fut, future_samples[i], color='tab:blue', alpha=0.1)
    
    # Plot Percentiles
    median = np.percentile(future_samples, 50, axis=0)
    p5 = np.percentile(future_samples, 5, axis=0)
    p95 = np.percentile(future_samples, 95, axis=0)
    
    plt.plot(t_fut, median, color='tab:blue', linewidth=2, linestyle='--', label='Median Prediction')
    plt.fill_between(t_fut, p5, p95, color='tab:blue', alpha=0.2, label='90% Confidence Interval')
    
    # Clinical Range indicators
    plt.axhspan(70, 180, color='green', alpha=0.1, label='Target Range')
    plt.axhline(70, color='red', linestyle=':', alpha=0.5, label='Hypo Threshold')
    
    plt.title(title)
    plt.xlabel("Minutes from Now")
    plt.ylabel("Glucose (mg/dL)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # Save or show
    plt.savefig("latest_forecast.png")
    print("Forecast plot saved to 'latest_forecast.png'")

def plot_dose_comparison(history_glucose, dose_results: dict):
    """
    Compares different doses visually.
    dose_results: {'0.0U': [future_gv], '2.0U': [future_gv], ...}
    """
    plt.figure(figsize=(12, 6))
    
    hist_len = len(history_glucose)
    t_hist = np.arange(-hist_len, 0) * 5
    plt.plot(t_hist, history_glucose, color='black', linewidth=2, label='History')
    
    for dose_label, future_gv in dose_results.items():
        t_fut = np.arange(0, len(future_gv)) * 5
        plt.plot(t_fut, future_gv, label=f"Proposed Dose: {dose_label}")
        
    plt.axhspan(70, 180, color='green', alpha=0.1)
    plt.title("Dosing Counselor: What-If Comparison")
    plt.xlabel("Minutes from Now")
    plt.ylabel("Glucose (mg/dL)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig("dose_comparison.png")
    print("Dose comparison plot saved to 'dose_comparison.png'")
