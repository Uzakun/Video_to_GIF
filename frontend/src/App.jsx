// frontend/src/App.jsx
import { useState } from 'react';

export default function App() {
  const [prompt, setPrompt] = useState('');
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [gifs, setGifs] = useState([]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setGifs([]);

    try {
      const response = await fetch('http://127.0.0.1:5000/api/generate-gifs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt,
          youtube_url: youtubeUrl,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Something went wrong on the server.');
      }
      
      setGifs(data.gifs);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <h1 className="main-title gradient-text">
            AI Video to GIF
          </h1>
          <p className="subtitle">
            Transform YouTube videos into perfect GIFs with AI-powered captions ✨
          </p>
          <div className="features">
            <span className="feature-item">
              <div className="status-dot status-green"></div>
              AI Powered
            </span>
            <span className="feature-item">
              <div className="status-dot status-blue"></div>
              Smart Captions
            </span>
            <span className="feature-item">
              <div className="status-dot status-purple"></div>
              Instant Results
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="main-content">
        
        {/* Form */}
        <div className="form-container glass">
          <form onSubmit={handleSubmit} className="form">
            
            {/* Inputs */}
            <div className="input-grid">
              <div className="input-group">
                <label className="input-label">
                  🎯 What moments do you want?
                </label>
                <input
                  type="text"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className="input-field"
                  placeholder="funny moments, epic fails, quotes..."
                  required
                />
              </div>
              
              <div className="input-group">
                <label className="input-label">
                  🎬 YouTube URL
                </label>
                <input
                  type="url"
                  value={youtubeUrl}
                  onChange={(e) => setYoutubeUrl(e.target.value)}
                  className="input-field"
                  placeholder="https://www.youtube.com/watch?v=..."
                  required
                />
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="submit-button"
            >
              {isLoading ? (
                <div className="button-loading">
                  <div className="spinner"></div>
                  Creating your GIFs...
                </div>
              ) : (
                '🚀 Create GIFs'
              )}
            </button>
          </form>
        </div>

        {/* Error */}
        {error && (
          <div className="error-container">
            <div className="error-box">
              <div className="error-content">
                <span>⚠️</span>
                <span>{error}</span>
              </div>
            </div>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="loading-section">
            <div className="loading-card glass-card">
              <div className="loading-spinner"></div>
              <h3 className="loading-title">Creating Magic...</h3>
              <p className="loading-text">Analyzing video and generating GIFs</p>
            </div>
          </div>
        )}

        {/* Results */}
        {gifs.length > 0 && (
          <div className="results-section animate-fade-up">
            <div className="results-header">
              <h2 className="results-title gradient-text-green">
              Your GIFs are Ready!
              </h2>
              <p className="results-subtitle">
                {gifs.length} amazing GIFs created with AI-powered captions
              </p>
            </div>
            
            <div className="gif-grid">
              {gifs.map((gif, index) => (
                <div 
                  key={index} 
                  className="gif-card glass-card"
                >
                  {/* GIF Image */}
                  <div className="gif-image-container">
                    <img 
                      src={gif} 
                      alt={`GIF ${index + 1}`} 
                      className="gif-image"
                    />
                    <div className="gif-number">
                      #{index + 1}
                    </div>
                  </div>
                  
                  {/* Download Button */}
                  <div className="gif-content">
                    <h3 className="gif-title">AI Generated GIF</h3>
                    <p className="gif-description">Perfect moment with smart captions</p>
                    <a
                      href={gif}
                      download={`gif-${index + 1}.gif`}
                      className="download-button"
                    >
                      📥 Download GIF
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

    </div>
  );
}