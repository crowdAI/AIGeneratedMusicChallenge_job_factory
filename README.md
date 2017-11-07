![CrowdAI-Logo](https://github.com/crowdAI/crowdai/raw/master/app/assets/images/misc/crowdai-logo-smile.svg?sanitize=true)
# CriteoAdPlacementChallenge_job_factory

Implementation of a CrowdAI Job Factory for the [Criteo Ad PlacementChallenge](https://www.crowdai.org/challenges/nips-17-workshop-criteo-ad-placement-challenge) on [CrowdAI](https://www.crowdai.org)

# Installation Instructions
```
sudo apt-get install redis-server
git clone git@github.com:spMohanty/CriteoAdPlacementChallenge_job_factory.git
cd CriteoAdPlacementChallenge_job_factory
pip install -r requirements.txt
python run.py
# Then in a separate tab
rqworker
# Then in a separate tab
rq-dashboard
```

# Author
S.P. Mohanty <sharada.mohanty@epfl.ch>
