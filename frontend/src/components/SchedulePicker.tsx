import React, { useState, useEffect, ChangeEvent, FormEvent } from 'react';
import { format, parseISO } from 'date-fns';

interface SchedulePickerProps {
  /** Initial datetime value as ISO string */
  initialDateTime?: string;
  /** Minimum date-time allowed (ISO string) */
  minDateTime?: string;
  /** Maximum date-time allowed (ISO string) */
  maxDateTime?: string;
  /** Callback when user picks date & time */
  onSchedule: (isoDateTime: string) => void;
}

/**
 * SchedulePicker
 * Renders date and time inputs for scheduling uploads.
 * Ensures valid ISO datetime output, enforces min/max constraints, accessible and responsive.
 */
const SchedulePicker: React.FC<SchedulePickerProps> = ({
  initialDateTime,
  minDateTime,
  maxDateTime,
  onSchedule,
}) => {
  // Derive local state
  const [date, setDate] = useState<string>('');
  const [time, setTime] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  // Initialize from initialDateTime
  useEffect(() => {
    if (initialDateTime) {
      try {
        const dt = parseISO(initialDateTime);
        setDate(format(dt, 'yyyy-MM-dd'));
        setTime(format(dt, 'HH:mm'));
      } catch {
        // ignore
      }
    }
  }, [initialDateTime]);

  // Validate combined datetime
  const validateAndSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!date || !time) {
      setError('Please select both date and time.');
      return;
    }

    const iso = `${date}T${time}:00`; // seconds appended
    // Enforce min/max if provided
    if (minDateTime && iso < minDateTime) {
      setError(`Scheduled time must be after ${minDateTime.replace('T', ' ')}`);
      return;
    }
    if (maxDateTime && iso > maxDateTime) {
      setError(`Scheduled time must be before ${maxDateTime.replace('T', ' ')}`);
      return;
    }

    onSchedule(iso);
  };

  return (
    <form onSubmit={validateAndSubmit} className="space-y-4 p-4 bg-white rounded shadow">
      <h2 className="text-xl font-semibold">Schedule Upload</h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Date input */}
        <div>
          <label htmlFor="schedule-date" className="block text-sm font-medium">
            Date <span className="text-red-500">*</span>
          </label>
          <input
            id="schedule-date"
            type="date"
            value={date}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setDate(e.target.value)}
            min={minDateTime ? minDateTime.slice(0, 10) : undefined}
            max={maxDateTime ? maxDateTime.slice(0, 10) : undefined}
            required
            className="mt-1 block w-full border border-gray-300 rounded p-2 focus:outline-none focus:ring focus:border-blue-300"
          />
        </div>

        {/* Time input */}
        <div>
          <label htmlFor="schedule-time" className="block text-sm font-medium">
            Time <span className="text-red-500">*</span>
          </label>
          <input
            id="schedule-time"
            type="time"
            value={time}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setTime(e.target.value)}
            required
            className="mt-1 block w-full border border-gray-300 rounded p-2 focus:outline-none focus:ring focus:border-blue-300"
          />
        </div>
      </div>

      {/* Error */}
      {error && <p className="text-red-600 text-sm">{error}</p>}

      {/* Submit */}
      <button
        type="submit"
        className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700"
      >
        Set Schedule
      </button>
    </form>
  );
};

export default SchedulePicker;
