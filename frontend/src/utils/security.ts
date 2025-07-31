// src/utils/security.ts

/**
 * Sanitizes user input by removing potentially dangerous HTML/script content
 * and encoding special characters to prevent XSS attacks
 */
export const sanitizeInput = (input: string): string => {
    if (typeof input !== 'string') return '';
    
    return input
      // Remove script tags and their content
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
      // Remove potentially dangerous HTML tags
      .replace(/<\/?(?:iframe|object|embed|form|input|script|style|link|meta)[^>]*>/gi, '')
      // Encode remaining angle brackets
      .replace(/[<>]/g, (match) => {
        return match === '<' ? '&lt;' : '&gt;';
      })
      // Remove null bytes
      .replace(/\0/g, '')
      // Limit length to prevent DOS attacks
      .slice(0, 10000);
  };
  
  /**
   * Validates and sanitizes HTML content for safe display
   */
  export const sanitizeHtml = (html: string): string => {
    if (typeof html !== 'string') return '';
    
    // Allow only safe HTML tags
    const allowedTags = ['p', 'br', 'strong', 'em', 'u', 'span', 'div'];
    const tagRegex = /<\/?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>/g;
    
    return html.replace(tagRegex, (match, tagName) => {
      if (allowedTags.includes(tagName.toLowerCase())) {
        // Remove any event handlers from allowed tags
        return match.replace(/\s*on\w+\s*=\s*["'][^"']*["']/gi, '');
      }
      return ''; // Remove disallowed tags
    });
  };
  
  /**
   * Validates email format
   */
  export const isValidEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email) && email.length <= 254;
  };
  
  /**
   * Validates URL format and protocol
   */
  export const isValidUrl = (url: string): boolean => {
    try {
      const urlObj = new URL(url);
      return ['http:', 'https:'].includes(urlObj.protocol);
    } catch {
      return false;
    }
  };
  
  /**
   * Escapes special characters in a string for use in regex
   */
  export const escapeRegex = (string: string): string => {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  };
  
  /**
   * Validates that a string contains only allowed characters
   */
  export const validateAllowedCharacters = (
    input: string, 
    allowedPattern: RegExp = /^[a-zA-Z0-9\s\-_.,!?()]*$/
  ): boolean => {
    return allowedPattern.test(input);
  };
  
  /**
   * Rate limiting helper - tracks attempts per identifier
   */
  class RateLimiter {
    private attempts: Map<string, number[]> = new Map();
    
    /**
     * Check if an identifier has exceeded the rate limit
     */
    isRateLimited(identifier: string, maxAttempts: number, windowMs: number): boolean {
      const now = Date.now();
      const attempts = this.attempts.get(identifier) || [];
      
      // Filter out attempts outside the time window
      const recentAttempts = attempts.filter(attempt => now - attempt < windowMs);
      
      // Update the attempts list
      this.attempts.set(identifier, recentAttempts);
      
      return recentAttempts.length >= maxAttempts;
    }
    
    /**
     * Record an attempt for an identifier
     */
    recordAttempt(identifier: string): void {
      const attempts = this.attempts.get(identifier) || [];
      attempts.push(Date.now());
      this.attempts.set(identifier, attempts);
    }
    
    /**
     * Clear attempts for an identifier
     */
    clearAttempts(identifier: string): void {
      this.attempts.delete(identifier);
    }
  }
  
  export const rateLimiter = new RateLimiter();
  
  /**
   * Generate a secure random string for CSRF tokens or IDs
   */
  export const generateSecureToken = (length: number = 32): string => {
    const array = new Uint8Array(length);
    crypto.getRandomValues(array);
    return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
  };
  
  /**
   * Content Security Policy helper
   */
  export const getCSPHeader = (): string => {
    return [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "media-src 'self' blob:",
      "connect-src 'self'",
      "font-src 'self' https://fonts.gstatic.com",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'"
    ].join('; ');
  };