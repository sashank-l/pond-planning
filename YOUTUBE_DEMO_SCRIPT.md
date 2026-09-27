# YouTube Demo Video Script (Max 5 Minutes)
**Course:** Computer Systems and Design (CSD) — Assignment 1  
**Project:** AI-based Village Pond Planning System  
**Author:** Lekkala Sashank (Roll: 12341330), IIT Tirupati  
**Target Video Duration:** ~4 minutes 30 seconds (Well under 5-minute cap)

---

## Recording Setup Checklist (Before you hit Record)
1. **Browser Tab 1:** The Frontend UI open at `http://localhost:4209/` (or `http://10.1.75.51:4209/`).
2. **Browser Tab 2:** FastAPI Swagger documentation at `http://localhost:3209/docs`.
3. **Browser Tab 3:** Your GitHub repository: `https://github.com/sashank-l/pond-planning`.
4. **Recording tool:** OBS Studio / Windows Game Bar (`Win + Alt + R`) / Loom.
5. **Microphone check:** Clear audio, no background noise.

---

## Timestamped Speaking Script & Screen Actions

### [0:00 - 0:35] Part 1: Problem Statement & Motivation
* **What to show on screen:** Show the Frontend application header or GitHub repository title page.
* **What to say (Speak clearly and naturally):**
> "Hello everyone. My name is Sashank Lekkala, Roll Number 12341330 from IIT Tirupati. Today I am presenting my submission for CSD Assignment 1: an AI-based Village Pond Planning System.
> 
> In rural, rain-fed agricultural areas across India, almost 75% of annual rainfall is lost as rapid surface runoff in just six to eight weeks of the monsoon. Village farm ponds are crucial for capturing this runoff and recharging groundwater, but planning where to dig a pond is traditionally a manual, subjective, and slow process requiring expensive surveyor visits.
> 
> Our system automates this completely. A planner uploads a standard contour map—in KML or KMZ format—or selects a plot on an interactive map. In just a few seconds, the system calculates the optimal pond location, delineates the upstream catchment boundary, and estimates the harvestable water volume."

---

### [0:35 - 1:40] Part 2: Technical Architecture & Core Algorithms
* **What to show on screen:** Switch to GitHub repo or a diagram / code view of `app/dem/` and `app/terrain/`.
* **What to say:**
> "Let's take a look under the hood at the computational pipeline. The backend is built with FastAPI and runs on Python 3.12 without heavy GIS runtimes like GDAL or ArcGIS, keeping memory footprint under 150 MB.
> 
> The pipeline consists of five key algorithmic stages:
> 
> 1. **Contour Ingestion & DEM Building:** We parse the KML contour lines, reproject coordinates into the local Universal Transverse Mercator (UTM) zone for metric accuracy, and use SciPy's Delaunay triangulation to interpolate a continuous Digital Elevation Model. We've built in an auto-coarsening safeguard so very dense grids never exceed 500,000 cells or trigger an Out-Of-Memory kill.
> 
> 2. **Priority-Flood Depression Filling:** Raw interpolated DEMs have false local sinks that trap water routing. We run Wang & Liu's priority-flood algorithm using a min-heap in O(N log N) time to guarantee continuous downward drainage.
> 
> 3. **Vectorised D8 Flow Routing:** Water flows to the steepest downslope neighbor among eight surrounding cells. By vectorizing the gradient calculations using NumPy array slicing across all directions at once, we evaluate a 20,000-cell grid in under 40 milliseconds.
> 
> 4. **Flow Accumulation via Kahn's Topological Sort:** Since the filled flow field is a Directed Acyclic Graph, we resolve accumulation in exact O(N) time without recursion.
> 
> 5. **Pond Site Selection & Catchment BFS:** A pond needs both substantial upstream drainage and natural concavity. We use a multi-criteria score weighting 70% flow accumulation and 30% depression depth. From the top-scoring cell, we run an inverse Breadth-First Search upstream to extract the exact contributing watershed boundary as a GeoJSON polygon."

---

### [1:40 - 3:30] Part 3: Live Demonstration of the Frontend & Map Visualization
* **What to show on screen:** Switch to the live web interface (`http://localhost:4209/` or `http://10.1.75.51:4209/`).
* **What to say & do (Follow along with clicks):**
> "Now let's jump into the live web application.
> 
> Here on port 4209 is our interactive map interface built with Leaflet.js. In the top right, we can seamlessly toggle between high-resolution Satellite Imagery and standard OpenStreetMap tiles.
> 
> Planners have two ways to input land area:
> First, they can click 'Draw Bounding Box on Map' *(click the button and draw a box on the map)* to demarcate any specific agricultural plot or survey boundary.
> 
> Second, they can upload their own survey `.kml` or `.kmz` file, or click this button here: 'Use Demo Contour' *(click the 'Use Demo Contour' button)*. This automatically loads our reference 6.7 Megabyte contour dataset containing 1,355 contour polylines near Raipur, Chhattisgarh.
> 
> We have grid resolution options—we'll keep it at 20 metres for rapid response—and we click 'Generate Pond Plan' *(click the Generate button)*.
> 
> *(Wait 7-8 seconds while the loading spinner runs)*
> 
> And there we have it! In just 8.5 seconds, the complete hydrological analysis is rendered directly on the satellite map:
> 
> - **Pond Location:** Look at this pulsing blue water droplet marker. The system selected coordinates **21.2630° N, 81.2830° E** at an elevation of **268.2 metres**, precisely at the natural convergence point of the valley.
> - **Catchment Boundary:** This translucent cyan polygon outlines the entire upstream watershed—measuring exactly **2.96 hectares (29,600 square metres)**. Every drop of rain falling within this dashed perimeter naturally drains towards our selected pond site.
> - **Expected Water Volume:** Over on our metrics panel, based on the regional monsoon rainfall of 800 mm and a calibrated runoff coefficient of 0.45, the expected annual harvest is **10,656 cubic metres**, which is over **10.6 Million Litres of water**.
> - **Recommended Sizing:** Based on the catchment's 14.6-metre relief, the system automatically sizes the pond for a recommended depth of **3.0 metres** and a surface area of **3,552 square metres**.
> - We can also click 'Export GeoJSON' *(click Export GeoJSON)* to immediately download the watershed polygon for GIS software or field civil works."

---

### [3:30 - 4:10] Part 4: Backend API, Tests & Deployment Reliability
* **What to show on screen:** Switch to the Swagger Docs tab (`/docs`), and quickly show the terminal with 25 passing tests.
* **What to say:**
> "The backend also exposes a clean, production-ready REST API. Here in Swagger docs at port 3209, we have `POST /analyzeContour`, `GET /health`, and `GET /sampleKml`.
> 
> In terms of code quality, the entire codebase is covered by 25 automated unit and integration tests using pytest, verifying KML parsing, DEM boundary interpolation, depression fill physics, and HTTP error handling.
> 
> For deployment, the container runs a custom multi-port bridge connecting external mapped ports 3209 and 4209 to internal services on ports 3000 and 4000. An infinite supervisor loop and `@reboot` crontab entry guarantee 24/7 uptime without manual intervention."

---

### [4:10 - 4:40] Part 5: Conclusion & GitHub Repository
* **What to show on screen:** Switch to GitHub repository: `https://github.com/sashank-l/pond-planning`.
* **What to say:**
> "To conclude, the system successfully bridges advanced computational terrain analysis with practical rural water engineering. All code, tests, documentation, and the final ACM LaTeX report are publicly available on GitHub at `github.com/sashank-l/pond-planning`.
> 
> Thank you for watching!"

---

## Quick Recording Tips
- Keep your mouse movements steady and deliberate when clicking buttons and showing map polygons.
- Do a quick 15-second test recording first to verify audio levels.
- Upload to YouTube as **Public** (or **Unlisted**, but assignment asks for *Public*).
- Put the title as: `AI-based Village Pond Planning System - CSD Assignment 1 Demo | IIT Tirupati`
- Paste the GitHub URL and Frontend URL in the YouTube video description!
