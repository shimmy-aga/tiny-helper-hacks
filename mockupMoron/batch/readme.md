### Tiny slightly bigger mockup generator 
- This script servers as a mockup gen tool, it can create mockups with the logo/design you put in the designated folders (.png, .eps, .webp, .jpg, .psd, .tif supported).
- It uses premade PSD's located in the `psd` folder. For every design you select a mockup is created.
- The logo's/designs are and should always be located in the `designs` folder.
- You can add more custom made PSD's, as long as the layout is correct  


### QUICK START
1. Place your designs in the correct format in the `designs` folder
2. Optional: Place extra custom PSD's in the `psd` folder, make sure `config.json` matches with your PSD layout
3. If not already empty, clear the `out` folder
4. In `start.bat`, set the PS_PATH to adobe's .exe file and the JSX_PATH to the location of your environments root (where this project lives)
4. Run the .bat file in the root folder
5. Your new mockups now live in the `out` folder