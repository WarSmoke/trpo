#coding=utf-8
import tensorflow as tf
from agent.agent_parallel import TRPOAgentParallel
import parameters as pms

# Flags for defining the tf.train.ClusterSpec
tf.app.flags.DEFINE_string("ps_hosts", "127.0.0.1:2223",
                           "Comma-separated list of hostname:port pairs")
tf.app.flags.DEFINE_string("worker_hosts", "127.0.0.1:2226",
                           "Comma-separated list of hostname:port pairs")

# Flags for defining the tf.train.Server
tf.app.flags.DEFINE_string("job_name", "worker", "ps or worker")
tf.app.flags.DEFINE_integer("task_index", 0, "Index of task within the job")

FLAGS = tf.app.flags.FLAGS

def main(_):
    ps_hosts = FLAGS.ps_hosts.split(',')
    worker_hosts = FLAGS.worker_hosts.split(',')

    # Create a cluster from the parameter server and worker hosts.
    cluster = tf.train.ClusterSpec({"ps": ps_hosts, "worker": worker_hosts})

    # Create and start a server for the local task.
    # 创建并启动服务
    # 其参数中使用task_index 指定任务的编号
    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=0.1 / 3.0)
    server = tf.train.Server(cluster,
                           job_name=FLAGS.job_name,
                           task_index=FLAGS.task_index,
                            config=tf.ConfigProto(gpu_options=gpu_options))

    if FLAGS.job_name == "ps":
        server.join()
    elif FLAGS.job_name == "worker":
        # 将op 挂载到各个本地的worker上
        with tf.device(tf.train.replica_device_setter(
            worker_device="/job:worker/task:%d/cpu:%d" % (FLAGS.task_index, FLAGS.task_index),
            cluster=cluster)):
            agent = TRPOAgentParallel()
        global_step = tf.Variable(0 , trainable=False , name='step')
        saver = tf.train.Saver(max_to_keep=10)
        init_op = tf.initialize_all_variables()
        # Create a "supervisor", which oversees the training process.
        sv = tf.train.Supervisor(is_chief=(FLAGS.task_index == 0),
                             logdir="checkpoint",
                             init_op=init_op,
                             global_step=global_step,
                             saver=saver,
                             save_model_secs=60)

        # The supervisor takes care of session initialization, restoring from
        # a checkpoint, and closing when done or an error occurs.
        with sv.managed_session(server.target, config=tf.ConfigProto(log_device_placement=True, allow_soft_placement=True)) as sess:
            agent.session = sess
            agent.gf.session = sess
            agent.sff.session =sess
            if pms.train_flag:
                agent.learn()
            elif FLAGS.task_index == 0:
                agent.test(pms.checkpoint_file)
        # Ask for all the services to stop.
        sv.stop()

if __name__ == "__main__":
  tf.app.run()