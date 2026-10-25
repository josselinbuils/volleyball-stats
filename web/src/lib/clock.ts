/** A clock standing in for the video when the page holds none: the video's controls and playlists
 * drive it the same way, and the court's top view follows its time. `element` is what it scrolls to
 * and puts full screen. */
export class Clock extends EventTarget {
  #time = 0;
  #paused = true;
  #rate = 1;
  #frame = 0;
  #last = 0;
  readonly seeking = false;
  // Nothing to hear.
  muted = true;

  readonly element: HTMLElement;
  readonly duration: number;

  constructor(element: HTMLElement, duration: number) {
    super();
    this.element = element;
    this.duration = duration;
  }

  get currentTime(): number {
    return this.#time;
  }

  set currentTime(time: number) {
    this.#time = Math.min(this.duration, Math.max(0, time));
    for (const name of ['seeking', 'seeked', 'timeupdate']) {
      this.dispatchEvent(new Event(name));
    }
  }

  get paused(): boolean {
    return this.#paused;
  }

  get playbackRate(): number {
    return this.#rate;
  }

  set playbackRate(rate: number) {
    this.#rate = rate;
    this.dispatchEvent(new Event('ratechange'));
  }

  get parentElement(): HTMLElement {
    return this.element;
  }

  play(): Promise<void> {
    if (this.#paused) {
      this.#paused = false;
      this.#last = performance.now();
      this.#frame = requestAnimationFrame(this.#tick);
      this.dispatchEvent(new Event('play'));
    }
    return Promise.resolve();
  }

  pause(): void {
    if (!this.#paused) {
      this.#paused = true;
      cancelAnimationFrame(this.#frame);
      this.dispatchEvent(new Event('pause'));
    }
  }

  getBoundingClientRect(): DOMRect {
    return this.element.getBoundingClientRect();
  }

  scrollIntoView(options?: ScrollIntoViewOptions): void {
    this.element.scrollIntoView(options);
  }

  #tick = (now: number) => {
    this.#time = Math.min(this.duration, this.#time + ((now - this.#last) / 1000) * this.#rate);
    this.#last = now;
    this.dispatchEvent(new Event('timeupdate'));
    if (this.#time >= this.duration) {
      this.pause();
    } else {
      this.#frame = requestAnimationFrame(this.#tick);
    }
  };
}
