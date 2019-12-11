import torch
import numpy as np
import os

from model.engine.tester import do_testing
import utils.logger as lg
from utils.visdom_plots import VisdomLogger
from mujoco import build_agent
from model import build_model


def do_training(
        cfg,
        logger,
        output_results_dir,
        output_rec_dir,
        output_weights_dir
):
    # Build the agent
    agent = build_agent(cfg)

    # Build the model
    model = build_model(cfg, agent)
    device = torch.device(cfg.MODEL.DEVICE)
    model.to(device)

    # Set mode to training (aside from policy output, matters for Dropout, BatchNorm, etc.)
    model.train()

    # Set up visdom
    visdom = VisdomLogger(cfg.LOG.PLOT.DISPLAY_PORT)
    visdom.register_keys(['total_loss', 'average_sd', 'average_action', "reinforce_loss",
                          "objective_loss", "sd", "action_grad", "sd_grad"])
    for action_idx in range(model.policy_net.action_dim):
        visdom.register_keys(["action_" + str(action_idx)])

    # wrap screen recorder if testing mode is on
    if cfg.LOG.TESTING.ENABLED:
        visdom.register_keys(['test_reward'])
        # NOTE: wrappers here won't affect the PyTorch MuJoCo blocks
        from gym.wrappers.monitoring.video_recorder import VideoRecorder
        video_recorder = VideoRecorder(agent)

    # Collect losses here
    output = {"epoch": [], "objective_loss": []}

    # Start training
    for epoch_idx in range(cfg.MODEL.EPOCHS):
        batch_loss = torch.empty(cfg.MODEL.BATCH_SIZE, cfg.MODEL.POLICY.MAX_HORIZON_STEPS, dtype=torch.float64)
        batch_loss.fill_(np.nan)

        for episode_idx in range(cfg.MODEL.BATCH_SIZE):

            state = torch.DoubleTensor(agent.reset())
            for step_idx in range(cfg.MODEL.POLICY.MAX_HORIZON_STEPS):
                state, reward = model(state)
                batch_loss[episode_idx, step_idx] = -reward
                #if agent.is_done:
                #    break

        loss = model.policy_net.optimize(batch_loss)
        output["objective_loss"].append(loss["objective_loss"])
        output["epoch"].append(epoch_idx)

        if epoch_idx % cfg.LOG.PERIOD == 0:
            visdom.update(loss)

            clamped_sd = model.policy_net.get_clamped_sd()
            clamped_action = model.policy_net.get_clamped_action()

            visdom.update({'average_sd': np.mean(clamped_sd, axis=1)})
            visdom.update({'average_action': np.mean(clamped_action, axis=(1, 2)).squeeze()})

            for action_idx in range(model.policy_net.action_dim):
                visdom.set({'action_'+str(action_idx): clamped_action[action_idx, :, :]})
            if clamped_sd is not None:
                visdom.set({'sd': clamped_sd.transpose()})
            logger.info("REWARD: \t\t{} (iteration {})".format(loss["total_loss"], epoch_idx))

        if epoch_idx % cfg.LOG.PLOT.ITER_PERIOD == 0:
            visdom.do_plotting()

        if epoch_idx % cfg.LOG.CHECKPOINT_PERIOD == 0:
            torch.save(model.state_dict(),
                       os.path.join(output_weights_dir, 'iter_{}.pth'.format(epoch_idx)))

        if cfg.LOG.TESTING.ENABLED:
            if epoch_idx % cfg.LOG.TESTING.ITER_PERIOD == 0:
                #logger.info("TESTING ... ")
                video_recorder.path = os.path.join(output_rec_dir, "iter_{}.mp4".format(epoch_idx))
                test_rewards = []
                for _ in range(cfg.LOG.TESTING.COUNT_PER_ITER):
                    test_reward = do_testing(
                        cfg,
                        model,
                        agent,
                        video_recorder,
                        # first_state=state_xr.get_item(),
                    )
                    test_rewards.append(test_reward)
                #mean_reward = np.mean(test_rewards)
                #visdom.update({'test_reward': [np.mean(mean_reward)]})
                #logger.info("REWARD MEAN TEST: \t\t{}".format(mean_reward))
                model.train()
                # video_recorder.close()


    # Save outputs into log folder
    lg.save_dict_into_csv(output_results_dir, "output", output)
