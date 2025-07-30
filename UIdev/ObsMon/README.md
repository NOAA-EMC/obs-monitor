# React + Vite

This website has been constructed using React, Vite, and the tailwinds.css within a VS Code environment.  This is the source code that React & Vite use to create all the files necessary to build the website.  Those files are intentionally not stored within this repository.  All edits should be done on this code and the website rebuilt. 

Below is the default README contents with the locations of necessary VS Code plugins.  At bottom are some frequently used powershell commands related to development.


Default README contents:

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.


Frequently used powershell commands:

> npm install    # installs all necessary packages

> npm run dev    # Starts a localhost instance of the resulting website using these development files.
                 # Ctrl + MB1 on the localhost address in the terminal window will add a view of the localhost 
                 # results in the default browser.

> npm run build  # Build the finished website.  Files will be placed in a dist/ directory.  These files should  
                 # be moved to the web server.
