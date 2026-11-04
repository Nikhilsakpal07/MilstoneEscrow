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

// Helper to safely read env variables across Vite and Next.js
const getEnvVar = (viteKey: string, nextKey: string, fallback: string = ""): string => {
  try {
    const metaEnv = (import.meta as any)?.env
    if (metaEnv && metaEnv[viteKey]) return metaEnv[viteKey]
  } catch {}
  try {
    if (typeof process !== "undefined" && process.env && process.env[nextKey]) {
      return process.env[nextKey] as string
    }
  } catch {}
  return fallback
}

// Configuration loaded exclusively from environment variables (.env.local)
const firebaseConfig = {
  apiKey: getEnvVar("VITE_FIREBASE_API_KEY", "NEXT_PUBLIC_FIREBASE_API_KEY"),
  authDomain: getEnvVar("VITE_FIREBASE_AUTH_DOMAIN", "NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN"),
  projectId: getEnvVar("VITE_FIREBASE_PROJECT_ID", "NEXT_PUBLIC_FIREBASE_PROJECT_ID"),
  storageBucket: getEnvVar("VITE_FIREBASE_STORAGE_BUCKET", "NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET"),
  messagingSenderId: getEnvVar("VITE_FIREBASE_MESSAGING_SENDER_ID", "NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID"),
  appId: getEnvVar("VITE_FIREBASE_APP_ID", "NEXT_PUBLIC_FIREBASE_APP_ID"),
  measurementId: getEnvVar("VITE_FIREBASE_MEASUREMENT_ID", "NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID"),
}

// Initialize Firebase once
export const app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig)
export const auth = getAuth(app)

// OAuth Providers
export const googleProvider = new GoogleAuthProvider()
googleProvider.setCustomParameters({ prompt: "select_account" })

export const githubProvider = new GithubAuthProvider()
githubProvider.addScope("repo")
githubProvider.addScope("read:user")

// Auth Helper Functions
export const loginWithEmail = (email: string, pass: string) =>
  signInWithEmailAndPassword(auth, email, pass)

export const signupWithEmail = (email: string, pass: string) =>
  createUserWithEmailAndPassword(auth, email, pass)

export const loginWithGoogle = () => signInWithPopup(auth, googleProvider)

export const loginWithGithub = () => signInWithPopup(auth, githubProvider)

export const logoutUser = () => signOut(auth)

export const subscribeToAuthChanges = (callback: (user: User | null) => void) =>
  onAuthStateChanged(auth, callback)
