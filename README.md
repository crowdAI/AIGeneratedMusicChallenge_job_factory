![CrowdAI-Logo](https://github.com/crowdAI/crowdai/raw/master/app/assets/images/misc/crowdai-logo-smile.svg?sanitize=true)
# AIGeneratedMusicChallenge_job_factory

Implementation of a CrowdAI Job Factory for the [AI Generated Music Challenge](https://www.crowdai.org/challenges/ai-generated-music-challenge) on [CrowdAI](https://www.crowdai.org)

# Installation Instructions
```
sudo apt-get install redis-server
git clone git@github.com:crowdai/AIGeneratedMusicChallenge_job_factory.git
cd AIGeneratedMusicChallenge_job_factory
pip install -r requirements.txt
python run.py
# Then in a separate tab
rqworker -c settings
# Then in a separate tab
rq-dashboard
```

# Author
S.P. Mohanty <sharada.mohanty@epfl.ch>
