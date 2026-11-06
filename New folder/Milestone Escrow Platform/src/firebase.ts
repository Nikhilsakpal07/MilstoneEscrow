import { initializeApp, getApps, getApp } from "firebase/app"
import {
  getAuth,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  GoogleAuthProvider,
  GithubAuthProvider,
  signOut,
  onAuthStateChanged,
  type User,
} from "firebase/auth"

export type { User }

// Static property access required for Webpack (Next.js) & Vite to inline environment variables
const getFirebaseConfig = () => {
  const apiKey =
    process.env.NEXT_PUBLIC_FIREBASE_API_KEY ||
    (typeof import.meta !== "undefined" && (import.meta as any)?.env?.VITE_FIREBASE_API_KEY) ||
    ""

  const authDomain =
    process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ||
    (typeof import.meta !== "undefined" && (import.meta as any)?.env?.VITE_FIREBASE_AUTH_DOMAIN) ||
    ""

  const projectId =
    process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ||
    (typeof import.meta !== "undefined" && (import.meta as any)?.env?.VITE_FIREBASE_PROJECT_ID) ||
    ""

  const storageBucket =
    process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET ||
    (typeof import.meta !== "undefined" && (import.meta as any)?.env?.VITE_FIREBASE_STORAGE_BUCKET) ||
    ""

  const messagingSenderId =
    process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID ||
    (typeof import.meta !== "undefined" && (import.meta as any)?.env?.VITE_FIREBASE_MESSAGING_SENDER_ID) ||
    ""

  const appId =
    process.env.NEXT_PUBLIC_FIREBASE_APP_ID ||
    (typeof import.meta !== "undefined" && (import.meta as any)?.env?.VITE_FIREBASE_APP_ID) ||
    ""

  const measurementId =
    process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID ||
    (typeof import.meta !== "undefined" && (import.meta as any)?.env?.VITE_FIREBASE_MEASUREMENT_ID) ||
    ""

  return {
    apiKey,
    authDomain,
    projectId,
    storageBucket,
    messagingSenderId,
    appId,
    measurementId,
  }
}

export const firebaseConfig = getFirebaseConfig()

// Initialize Firebase safely without crashing if env vars haven't reloaded yet
let appInstance: any = null
let authInstance: any = null

const isConfigValid = Boolean(firebaseConfig.apiKey && firebaseConfig.apiKey.trim().length > 5)

if (isConfigValid) {
  try {
    appInstance = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig)
    authInstance = getAuth(appInstance)
  } catch (err) {
    console.warn("[Firebase] Could not initialize Firebase instance:", err)
  }
} else {
  console.warn(
    "[Firebase] NEXT_PUBLIC_FIREBASE_API_KEY is not loaded. If you recently edited .env.local, restart 'npm run dev'."
  )
}

export const app = appInstance
export const auth = authInstance

// OAuth Providers
export const googleProvider = new GoogleAuthProvider()
googleProvider.setCustomParameters({ prompt: "select_account" })

export const githubProvider = new GithubAuthProvider()
githubProvider.addScope("repo")
githubProvider.addScope("read:user")

// Auth Helper Functions with safety guards
export const loginWithEmail = async (email: string, pass: string) => {
  if (!auth) {
    throw new Error(
      "Firebase Auth is not initialized. Please restart 'npm run dev' to reload .env.local."
    )
  }
  return signInWithEmailAndPassword(auth, email, pass)
}

export const signupWithEmail = async (email: string, pass: string) => {
  if (!auth) {
    throw new Error(
      "Firebase Auth is not initialized. Please restart 'npm run dev' to reload .env.local."
    )
  }
  return createUserWithEmailAndPassword(auth, email, pass)
}

export const loginWithGoogle = async () => {
  if (!auth) {
    throw new Error(
      "Firebase Auth is not initialized. Please restart 'npm run dev' to reload .env.local."
    )
  }
  return signInWithPopup(auth, googleProvider)
}

export const loginWithGithub = async () => {
  if (!auth) {
    throw new Error(
      "Firebase Auth is not initialized. Please restart 'npm run dev' to reload .env.local."
    )
  }
  return signInWithPopup(auth, githubProvider)
}

export const logoutUser = async () => {
  if (!auth) return
  return signOut(auth)
}

export const subscribeToAuthChanges = (callback: (user: User | null) => void) => {
  if (!auth) {
    callback(null)
    return () => {}
  }
  return onAuthStateChanged(auth, callback)
}
