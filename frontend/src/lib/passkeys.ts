import {
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser'

export async function registerPasskey(optionsPayload: Record<string, unknown>) {
  const { sessionKey, ...options } = optionsPayload
  if (!sessionKey || typeof sessionKey !== 'string') {
    throw new Error('Passkey session expired')
  }
  const credential = await startRegistration({
    optionsJSON: options as PublicKeyCredentialCreationOptionsJSON,
  })
  return { sessionKey, credential }
}

export async function authenticatePasskey(optionsPayload: Record<string, unknown>) {
  const { sessionKey, ...options } = optionsPayload
  if (!sessionKey || typeof sessionKey !== 'string') {
    throw new Error('Passkey session expired')
  }
  const credential = await startAuthentication({
    optionsJSON: options as PublicKeyCredentialRequestOptionsJSON,
  })
  return { sessionKey, credential }
}
