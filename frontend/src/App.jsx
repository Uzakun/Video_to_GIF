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
    <div className="min-h-screen bg-gray-900 text-white flex flex-col items-center p-4 sm:p-6 md:p-10">
      <div className="w-full max-w-2xl">
        <header className="text-center mb-8">
          <h1 className="text-4xl sm:text-5xl font-bold mb-2">AI Video to GIF Generator ⚡️</h1>
          <p className="text-lg text-gray-400">Turn any YouTube video into captioned GIFs instantly.</p>
        </header>

        <main>
          <form onSubmit={handleSubmit} className="bg-gray-800 p-6 rounded-lg shadow-lg space-y-4">
            <div>
              <label htmlFor="prompt" className="block text-sm font-medium text-gray-300 mb-1">
                GIF Theme or Quote
              </label>
              <input
                type="text"
                id="prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded-md p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                placeholder="e.g., 'funny moments', 'are you not entertained?'"
                required
              />
            </div>
            <div>
              <label htmlFor="youtube_url" className="block text-sm font-medium text-gray-300 mb-1">
                YouTube URL
              </label>
              <input
                type="url"
                id="youtube_url"
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded-md p-2 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                placeholder="https://www.youtube.com/watch?v=..."
                required
              />
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-indigo-600 hover:bg-indigo-700 font-bold py-3 px-4 rounded-md disabled:bg-gray-500 disabled:cursor-not-allowed transition-colors duration-300"
            >
              {isLoading ? 'Generating...' : 'Create GIFs'}
            </button>
          </form>

          {error && <div className="mt-6 bg-red-900/50 text-red-300 p-4 rounded-md">{error}</div>}

          {isLoading && (
            <div className="mt-8 text-center">
              <p className="text-xl">Brewing your GIFs... please wait a moment! 🧙‍♂️</p>
            </div>
          )}

          {gifs.length > 0 && (
            <div className="mt-8">
              <h2 className="text-2xl font-bold mb-4 text-center">Your GIFs are Ready!</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {gifs.map((gif, index) => (
                  <div key={index} className="bg-gray-800 rounded-lg overflow-hidden shadow-lg">
                    <img src={gif} alt={`Generated GIF ${index + 1}`} className="w-full h-auto" />
                    <a
                      href={gif}
                      download
                      className="block text-center bg-indigo-600 hover:bg-indigo-700 w-full py-2 font-semibold transition-colors duration-300"
                    >
                      Download
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}