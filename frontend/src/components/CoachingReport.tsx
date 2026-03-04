interface Props {
  summary: string
  strengths: string[]
  weaknesses: string[]
  recommendations: string[]
}

export default function CoachingReport({ summary, strengths, weaknesses, recommendations }: Props) {
  if (!summary && !strengths.length && !weaknesses.length && !recommendations.length) {
    return (
      <div className="text-sm text-gray-500 italic">No AI feedback available.</div>
    )
  }

  return (
    <div className="space-y-4">
      {summary && (
        <p className="text-gray-300 leading-relaxed">{summary}</p>
      )}

      {strengths.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-green-400 mb-2">💪 Strengths</h4>
          <ul className="space-y-1">
            {strengths.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                <span className="text-green-500 mt-0.5">•</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {weaknesses.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-yellow-400 mb-2">📉 Weaknesses</h4>
          <ul className="space-y-1">
            {weaknesses.map((w, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                <span className="text-yellow-500 mt-0.5">•</span>
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}

      {recommendations.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-blue-400 mb-2">💡 Recommendations</h4>
          <ul className="space-y-1">
            {recommendations.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                <span className="text-blue-500 mt-0.5">{i + 1}.</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
