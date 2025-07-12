import React, { useState, useEffect } from 'react';

type Platform = 'YouTube' | 'TikTok' | 'Instagram';

interface PlatformSelectorProps {
  /** Initially selected platforms */
  initialSelected?: Platform[];
  /** Callback when selection changes */
  onChange: (selected: Platform[]) => void;
}

/**
 * PlatformSelector
 * Renders checkboxes for social platforms and manages selection state.
 * Ensures at least one platform is selected before proceeding.
 */
const PlatformSelector: React.FC<PlatformSelectorProps> = ({ initialSelected = [], onChange }) => {
  // Local state for selected platforms
  const [selected, setSelected] = useState<Platform[]>(initialSelected);
  const [error, setError] = useState<string | null>(null);

  // Platforms to choose from
  const options: Platform[] = ['YouTube', 'TikTok', 'Instagram'];

  // Notify parent whenever selection updates
  useEffect(() => {
    onChange(selected);
    // Clear error if at least one selected
    if (selected.length > 0) setError(null);
  }, [selected, onChange]);

  // Toggle a platform in selection
  const togglePlatform = (platform: Platform) => {
    setSelected(prev => {
      if (prev.includes(platform)) {
        return prev.filter(p => p !== platform);
      }
      return [...prev, platform];
    });
  };

  // Validate before form submission or navigation
  const validate = () => {
    if (selected.length === 0) {
      setError('Please select at least one platform.');
      return false;
    }
    return true;
  };

  return (
    <div className="p-4 bg-white rounded shadow space-y-2">
      <h2 className="text-xl font-semibold">Select Platforms</h2>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {options.map(platform => (
          <label key={platform} className="flex items-center space-x-2">
            <input
              type="checkbox"
              name="platforms"
              value={platform}
              checked={selected.includes(platform)}
              onChange={() => togglePlatform(platform)}
              className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
            />
            <span className="text-sm font-medium">{platform}</span>
          </label>
        ))}
      </div>

      {/* Error message if no platform selected */}
      {error && <p className="text-red-600 text-sm">{error}</p>}

      {/* Optional validate button demonstration */}
      <button
        type="button"
        onClick={validate}
        className="mt-2 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
      >
        Confirm Selection
      </button>
    </div>
  );
};

export default PlatformSelector;
