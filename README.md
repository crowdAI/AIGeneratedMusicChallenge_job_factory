![CrowdAI-Logo](https://github.com/crowdAI/crowdai/raw/master/app/assets/images/misc/crowdai-logo-smile.svg?sanitize=true)
# Learning2RunNIPS2017_job_factory

Implementation of a CrowdAI Job Factory for the [NIPS 2017 Learning to Run Challenge](https://www.crowdai.org/organizers/stanford-neuromuscular-biomechanics-laboratory/challenges/nips-2017-learning-to-run) on [CrowdAI](https://www.crowdai.org)

# Installation Instructions
```
sudo apt-get install redis-server
git clone git@github.com:spMohanty/Learning2RunNIPS2017_job_factory.git
cd Learning2RunNIPS2017_job_factory
pip install -r requirements.txt
python run.py
# Then in a separate tab
rqworker -c settings
# Then in a separate tab
rq-dashboard
```

# Author
S.P. Mohanty <sharada.mohanty@epfl.ch>
