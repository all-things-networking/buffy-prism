import matplotlib.pyplot as plt
import numpy as np


def plot_sprt_results(results):
    """Plot SPRT results."""
    fig, axes = plt.subplots(1, 2, figsize=(20, 6))

    # # Distribution plots
    # z_grid = np.linspace(0, 1, 200)
    # f0 = create_beta_density(params.a0, params.b0)
    # f1 = create_beta_density(params.a1, params.b1)
    #
    # axes[0].plot(z_grid, f0(z_grid), 'b-', lw=2,
    #              label=f'$f_0 = \\text{{Beta}}({params.a0},{params.b0})$')
    # axes[0].plot(z_grid, f1(z_grid), 'r-', lw=2,
    #              label=f'$f_1 = \\text{{Beta}}({params.a1},{params.b1})$')
    # axes[0].fill_between(z_grid, 0,
    #                      np.minimum(f0(z_grid), f1(z_grid)),
    #                      alpha=0.3, color='purple', label='overlap')
    # if title:
    #     axes[0].set_title(title, fontsize=20)
    # axes[0].set_xlabel('z', fontsize=16)
    # axes[0].set_ylabel('density', fontsize=16)
    # axes[0].legend(fontsize=14)

    # Stopping times
    max_n = results['stopping_times'].max() #min(results['stopping_times'].max(), 10001)
    bins = max_n // 100
    axes[0].hist(results['stopping_times'], bins=bins,
                 color="steelblue", alpha=0.8, edgecolor="black")
    axes[0].set_title(f'stopping times (μ={results["stopping_times"].mean():.1f})',
                      fontsize=16)
    axes[0].set_xlabel('n', fontsize=16)
    axes[0].set_ylabel('frequency', fontsize=16)
    axes[0].set_xlim(0, max_n)

    # Confusion matrix
    plot_confusion_matrix(results, axes[1])

    plt.tight_layout()
    plt.show()


def plot_confusion_matrix(results, ax):
    """Plot confusion matrix for SPRT results."""
    f0_correct = np.sum(results['truth_h_minus'] & results['decisions_h_minus'])
    f0_incorrect = np.sum(results['truth_h_minus'] & (~results['decisions_h_minus']))
    f1_correct = np.sum((~results['truth_h_minus']) & (~results['decisions_h_minus']))
    f1_incorrect = np.sum((~results['truth_h_minus']) & results['decisions_h_minus'])

    confusion_data = np.array([[f0_correct, f0_incorrect],
                               [f1_incorrect, f1_correct]])
    row_totals = confusion_data.sum(axis=1, keepdims=True)

    im = ax.imshow(confusion_data, cmap='Blues', aspect='equal')
    ax.set_title(f'errors: I={results["type_I"]:.3f} II={results["type_II"]:.3f}',
                 fontsize=16)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(['accept $H_{-1}$', 'accept $H_{+1}$'], fontsize=14)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(['true $f_{-1}$', 'true $f_{+1}$'], fontsize=14)

    for i in range(2):
        for j in range(2):
            percent = confusion_data[i, j] / row_totals[i, 0] \
                if row_totals[i, 0] > 0 else 0
            color = 'white' if confusion_data[i, j] > confusion_data.max() * 0.5 \
                else 'black'
            ax.text(j, i, f'{confusion_data[i, j]}\n({percent:.1%})',
                    ha="center", va="center", color=color, fontweight='bold',
                    fontsize=14)

def plot_cr_results(results):
    """Plot CR results."""
    fig, axes = plt.subplots(1, 2, figsize=(20, 6))

    # Stopping times
    max_n = results['stopping_times'].max() #min(results['stopping_times'].max(), 10001)
    bins = max_n // 100
    axes[0].hist(results['stopping_times'], bins=bins,
                 color="steelblue", alpha=0.8, edgecolor="black")
    axes[0].set_title(f'stopping times (μ={results["stopping_times"].mean():.1f})',
                      fontsize=16)
    axes[0].set_xlabel('n', fontsize=16)
    axes[0].set_ylabel('frequency', fontsize=16)
    axes[0].set_xlim(0, max_n)

    # Confusion matrix
    plot_confusion_inconcl_matrix(results, axes[1])

    plt.tight_layout()
    plt.show()


def plot_confusion_inconcl_matrix(results, ax):
    """Plot confusion matrix for SPRT results."""
    f0_correct   = np.sum(results['truth_h_minus'] & (results['decisions_h_minus']))
    f0_inconcl   = np.sum(results['truth_h_minus'] & (results['decisions_inconcl']))
    f0_incorrect = np.sum(results['truth_h_minus'] & (results['decisions_h_plus']))
    f1_correct   = np.sum((~results['truth_h_minus']) & (results['decisions_h_plus']))
    f1_inconcl   = np.sum((~results['truth_h_minus']) & (results['decisions_inconcl']))
    f1_incorrect = np.sum((~results['truth_h_minus']) & (results['decisions_h_minus']))

    confusion_data = np.array([[f0_correct, f0_inconcl, f0_incorrect],
                               [f1_incorrect, f1_inconcl, f1_correct]])
    row_totals = confusion_data.sum(axis=1, keepdims=True)

    im = ax.imshow(confusion_data, cmap='Blues', aspect='equal')
    ax.set_title(f'errors: I={results["type_I"]:.3f} II={results["type_II"]:.3f}',
                 fontsize=16)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(['accept $H_{-1}$', 'inconclusive', 'accept $H_{+1}$'], fontsize=14)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(['true $f_{-1}$', 'true $f_{+1}$'], fontsize=14)

    for i in range(2):
        for j in range(3):
            percent = confusion_data[i, j] / row_totals[i, 0] \
                if row_totals[i, 0] > 0 else 0
            color = 'white' if confusion_data[i, j] > confusion_data.max() * 0.5 \
                else 'black'
            ax.text(j, i, f'{confusion_data[i, j]}\n({percent:.1%})',
                    ha="center", va="center", color=color, fontweight='bold',
                    fontsize=14)