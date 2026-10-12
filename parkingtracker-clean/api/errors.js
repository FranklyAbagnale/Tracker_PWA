/** Errors a provider adapter may throw. The handler turns them into HTTP responses. */

/** The provider has no account or key yet (the shipped stub throws this). */
export class NotConfiguredError extends Error {
  constructor(message = 'No lookup provider is configured') {
    super(message);
    this.name = 'NotConfiguredError';
  }
}

/** The provider failed or returned something unusable. Never include keys or plates in the message. */
export class ProviderError extends Error {
  constructor(message = 'The lookup provider failed') {
    super(message);
    this.name = 'ProviderError';
  }
}
