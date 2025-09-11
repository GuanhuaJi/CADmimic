# create & activate a conda env
conda create -n cad-gemini python=3.11 -y
conda activate cad-gemini

# install CadQuery (conda-forge) and Gemini API
conda install -c conda-forge cadquery -y
pip install -U google-genai