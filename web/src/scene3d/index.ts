import { mount } from '@/scene3d/scene';

// A script of its own, loaded only when the page shows the 3D view: it hands the page `mount`.
declare global {
  interface Window {
    VolleyScene?: { mount: typeof mount };
  }
}

window.VolleyScene = { mount };
