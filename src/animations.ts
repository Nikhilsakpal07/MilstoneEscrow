import { gsap } from "gsap"

/**
 * Screen transition: subtle vertical slide + clean alpha fade
 */
export function animateScreenEnter(target: HTMLElement | null) {
  if (!target) return
  gsap.fromTo(
    target,
    { opacity: 0, y: 16 },
    { opacity: 1, y: 0, duration: 0.45, ease: "power2.out" }
  )
}

/**
 * Landing page hero staggered entrance
 */
export function animateHeroEntrance(container: HTMLElement | null) {
  if (!container) return
  const elements = container.querySelectorAll(
    ".hero-signal, h1, p, .hero-cta, .landing-proof > span"
  )
  if (elements.length === 0) return

  gsap.fromTo(
    elements,
    { opacity: 0, y: 24 },
    {
      opacity: 1,
      y: 0,
      duration: 0.6,
      stagger: 0.08,
      ease: "power3.out",
    }
  )
}

/**
 * Staggered cards entrance (Metric cards, table rows, milestones)
 */
export function animateStaggerCards(container: HTMLElement | null, selector: string) {
  if (!container) return
  const items = container.querySelectorAll(selector)
  if (items.length === 0) return

  gsap.fromTo(
    items,
    { opacity: 0, y: 14 },
    {
      opacity: 1,
      y: 0,
      duration: 0.4,
      stagger: 0.05,
      ease: "power2.out",
    }
  )
}

/**
 * Toast / Alert pop-in animation
 */
export function animateToast(toastElement: HTMLElement | null) {
  if (!toastElement) return
  gsap.fromTo(
    toastElement,
    { opacity: 0, scale: 0.9, y: -20 },
    { opacity: 1, scale: 1, y: 0, duration: 0.4, ease: "back.out(1.7)" }
  )
}

/**
 * Attention pulse for security alert banners and risk indicators
 */
export function animateAlertPulse(target: HTMLElement | null) {
  if (!target) return
  gsap.fromTo(
    target,
    { scale: 0.98, opacity: 0.9 },
    {
      scale: 1,
      opacity: 1,
      duration: 0.8,
      repeat: 1,
      yoyo: true,
      ease: "sine.inOut",
    }
  )
}

/**
 * Button click ripple / press micro-interaction
 */
export function animateButtonPress(btn: HTMLElement | null) {
  if (!btn) return
  gsap.to(btn, {
    scale: 0.96,
    duration: 0.1,
    yoyo: true,
    repeat: 1,
    ease: "power1.inOut",
  })
}

