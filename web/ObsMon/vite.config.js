import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ command, mode }) => {
  return {
    plugins: [react()],
    base: command === 'build'
      ? '/gmb/gdas/radiance/esafford/obsmon/'
      : '/', // use root path for dev
  };
});

// import { defineConfig } from 'vite'
// import react from '@vitejs/plugin-react'

// // https://vite.dev/config/
// export default defineConfig({
//   base: mode === 'production'
//     ? '/gmb/gdas/radiance/esafford/obsmon/'
//     : '/', // localhost uses root
//   plugins: [react()],
// })
