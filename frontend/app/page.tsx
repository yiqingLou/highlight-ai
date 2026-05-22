"use client";

import { useEffect, useState } from "react";

type Highlight = {
  id: number;
  label: string;
  start_sec: number;
  end_sec: number;
  score: number;
  reason: string;
};

export default function Home() {
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/highlights")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setHighlights(data.highlights);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          highlight-ai
        </h1>
        <p className="text-gray-600 mb-8">
          AI-detected game highlights (demo data from backend)
        </p>

        {loading && <p className="text-gray-500">Loading...</p>}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded">
            <p className="font-semibold">Failed to load highlights</p>
            <p className="text-sm mt-1">{error}</p>
            <p className="text-sm mt-2 text-red-600">
              Make sure the backend is running at http://localhost:8000
            </p>
          </div>
        )}

        {!loading && !error && (
          <div className="space-y-3">
            {highlights.map((h) => (
              <div
                key={h.id}
                className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="flex justify-between items-start mb-2">
                  <h2 className="text-xl font-semibold text-gray-900">
                    {h.label}
                  </h2>
                  <span className="bg-yellow-100 text-yellow-800 text-sm font-bold px-3 py-1 rounded-full">
                    {h.score} pts
                  </span>
                </div>
                <p className="text-sm text-gray-500 mb-2">
                  {h.start_sec.toFixed(1)}s — {h.end_sec.toFixed(1)}s
                </p>
                <p className="text-sm text-gray-700">{h.reason}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}