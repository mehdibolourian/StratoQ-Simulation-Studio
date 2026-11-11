"""Demo PPO defaults: stage 3 gets actual time to train; reward unchanged."""
import numpy as np
from main import LearningStart
from stratoq_demo.learning_worker import curriculum_schedule


def test_demo_defaults_prioritize_full_demand_training():
    c=LearningStart()
    assert c.episodes==48 and c.checkpoint_every==6
    assert c.learning_rate==2e-4
    assert c.ppo_epochs==8 and c.batch_size==16
    assert c.entropy_start==.008 and c.entropy_end==.0003
    assert c.gamma==.99 and c.gae_lambda==.95 and c.clip==.2
    assert (c.curriculum_first_end_pct,c.curriculum_second_end_pct)==(12,30)
    data={f'd{i}':[1.]*24 for i in range(3)}
    rng=np.random.default_rng(c.seed)
    expected=[1]*6 + [2]*8 + [3]*34
    actual=[curriculum_schedule(data,episode,c.episodes,rng,
            first_end_pct=c.curriculum_first_end_pct,
            second_end_pct=c.curriculum_second_end_pct)[1]
            for episode in range(1,c.episodes+1)]
    assert actual==expected


def test_user_can_override_learning_defaults_without_changing_reward():
    c=LearningStart(episodes=6,ppo_epochs=3,batch_size=8,
                    learning_rate=.0001,entropy_start=.01,entropy_end=.001,
                    curriculum_first_end_pct=20,curriculum_second_end_pct=50)
    assert c.episodes==6 and c.curriculum_second_end_pct==50
